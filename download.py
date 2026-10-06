#!/usr/bin/env python3
"""manifest に載っている月のファイルを archive.epgdata.jp から取得し、SHA-256 を確かめる。

使い方:
  python3 download.py tokyo 2026-08                 # 東京の 2026年8月の全形式
  python3 download.py tokyo 2026-08 --format csv    # csv / sqlite / parquet のどれか
  python3 download.py tokyo 2025-01 2026-08 --format parquet --out data

地域は manifest.json の regions にあるもの（今は tokyo だけ）。ハッシュはこのリポジトリの
<地域>/manifest.json（Git の履歴に残っているもの）と照合し、合わないファイルは保存しない。
標準ライブラリだけで動く。
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

# Cloudflare は既定の Python-urllib の User-Agent を拒否するので、名乗ってから取得する。
USER_AGENT = "jp-epg-archive/1 (+https://github.com/epgdata/jp-epg-archive)"

FORMATS = {
    "sqlite": ("sqlite+zstd",),
    "csv": ("csv+zip",),
    "parquet": ("parquet:programmes", "parquet:aired"),
}


def months_between(first, last):
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    while (y, m) <= (ly, lm):
        yield "%04d-%02d" % (y, m)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch(url, path, sha256, size, attempts=3):
    """取得してハッシュとサイズを確かめる。通信が途中で切れたときのために取り直す。"""
    tmp = path + ".part"
    for attempt in range(1, attempts + 1):
        digest = hashlib.sha256()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response, open(tmp, "wb") as out:
                for chunk in iter(lambda: response.read(1 << 20), b""):
                    digest.update(chunk)
                    out.write(chunk)
            if digest.hexdigest() == sha256 and os.path.getsize(tmp) == size:
                os.replace(tmp, path)
                return
        except OSError as e:
            print("取得に失敗（%d/%d）: %s" % (attempt, attempts, e), file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        if attempt < attempts:
            time.sleep(5)
    raise SystemExit("ハッシュが合いません: %s" % url)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("region", help="地域（例: tokyo）")
    parser.add_argument("first", help="YYYY-MM")
    parser.add_argument("last", nargs="?", help="YYYY-MM（省略すると first の月だけ）")
    parser.add_argument("--format", choices=sorted(FORMATS), action="append",
                        help="取得する形式。複数回指定できる。省略するとすべて")
    parser.add_argument("--out", default=".", help="保存先のディレクトリ")
    parser.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)),
                        help="manifest.json のあるディレクトリ（このリポジトリ）")
    args = parser.parse_args()

    with open(os.path.join(args.root, "manifest.json"), encoding="utf-8") as f:
        regions = {r["region"]: r for r in json.load(f)["regions"]}
    if args.region not in regions:
        raise SystemExit("地域がありません: %s（あるのは %s）"
                         % (args.region, ", ".join(sorted(regions))))
    with open(os.path.join(args.root, regions[args.region]["manifest"]), encoding="utf-8") as f:
        manifest = json.load(f)
    by_month = {m["month"]: m for m in manifest["months"]}
    wanted = {fmt for name in (args.format or FORMATS) for fmt in FORMATS[name]}
    os.makedirs(args.out, exist_ok=True)
    missing = []
    for month in months_between(args.first, args.last or args.first):
        entry = by_month.get(month)
        if entry is None:
            missing.append(month)
            continue
        for f in entry["files"]:
            if f["format"] not in wanted:
                continue
            path = os.path.join(args.out, os.path.basename(f["path"]))
            print("取得: %s (%d バイト)" % (f["path"], f["bytes"]))
            fetch(manifest["base_url"] + f["path"], path, f["sha256"], f["bytes"])
    if missing:
        print("%s/manifest.json に無い月: %s" % (args.region, ", ".join(missing)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
