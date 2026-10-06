#!/usr/bin/env python3
"""archive.epgdata.jp の索引を、このリポジトリへ写す（--check では確かめるだけ）。

配布元のサーバが新しい月を公開するたびに実行し、変わった索引をコミットする。
地域の一覧（manifest.json）と、そこに載っている
各地域の索引（<地域>/manifest.json）を取り込む。配布ファイルは公開後に変えない
約束なので、次のどれかに当たる更新は受け付けずに失敗する。

- 既に載っているファイル（同じパス）のハッシュやサイズが変わる
- 載っていた地域や月が消える、または月の版が下がる
- 形式の版が変わる、地域名・パス・ハッシュの形が正しくない

新しく載ったファイルはダウンロードしてハッシュとサイズを確かめる。ここで確かめた
ハッシュが Git の履歴に残るので、後から配布元のファイルが差し替えられても気付ける。
標準ライブラリだけで動く。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

# Cloudflare は既定の Python-urllib の User-Agent を拒否するので、名乗ってから取得する。
USER_AGENT = "jp-epg-archive/1 (+https://github.com/epgdata/jp-epg-archive)"

REGION = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
FILE = re.compile(
    r"^(?P<region>[a-z][a-z0-9-]{0,30})/(?P<year>\d{4})/epg-(?P=region)-(?P<month>\d{4}-\d{2})"
    r"\.r(?P<revision>[1-9]\d*)\.(sqlite\.zst|csv\.zip|programmes\.parquet|aired\.parquet)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ManifestError(Exception):
    pass


def open_url(url, timeout):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout)


def fetch_json(url):
    with open_url(url, timeout=60) as response:
        return json.load(response)


def validate_root(old, new):
    """地域の一覧を検査する。"""
    if new.get("format_version") != 1:
        raise ManifestError("format_version が 1 ではない: %r" % new.get("format_version"))
    if not str(new.get("base_url", "")).startswith("https://"):
        raise ManifestError("base_url が https ではない")
    regions = new.get("regions")
    if not isinstance(regions, list):
        raise ManifestError("regions が無い")
    names = [r.get("region", "") for r in regions]
    if len(set(names)) != len(names) or not all(REGION.match(n) for n in names):
        raise ManifestError("地域名の形が正しくないか重複している: %r" % names)
    for r in regions:
        if r.get("manifest") != "%s/manifest.json" % r["region"]:
            raise ManifestError("地域の索引の場所が正しくない: %r" % r.get("manifest"))
    if old:
        missing = {r["region"] for r in old["regions"]} - set(names)
        if missing:
            raise ManifestError("地域が消えた: %s" % ", ".join(sorted(missing)))


def files_of(manifest):
    return {f["path"]: f for m in manifest.get("months", []) for f in m["files"]}


def validate(old, new, region):
    """地域の索引 new を検査し、新しく載ったファイルのリストを返す。"""
    if new.get("format_version") != 1:
        raise ManifestError("format_version が 1 ではない: %r" % new.get("format_version"))
    if new.get("region") != region:
        raise ManifestError("地域が合わない: %r" % new.get("region"))
    if not str(new.get("base_url", "")).startswith("https://"):
        raise ManifestError("base_url が https ではない")
    seen_months = set()
    for m in new["months"]:
        if not MONTH.match(m.get("month", "")) or m["month"] in seen_months:
            raise ManifestError("月の形が正しくないか重複している: %r" % m.get("month"))
        seen_months.add(m["month"])
        for f in m["files"]:
            match = FILE.match(f.get("path", ""))
            if (match is None or match["region"] != region or match["month"] != m["month"]
                    or match["year"] != m["month"][:4] or int(match["revision"]) != m["revision"]):
                raise ManifestError("パスが地域・月・版に合わない: %r" % f.get("path"))
            if not SHA256.match(f.get("sha256", "")) or not isinstance(f.get("bytes"), int):
                raise ManifestError("ハッシュかサイズが正しくない: %s" % f["path"])
    if old:
        new_months = {m["month"]: m for m in new["months"]}
        for m in old["months"]:
            if m["month"] not in new_months:
                raise ManifestError("月が消えた: %s" % m["month"])
            if new_months[m["month"]]["revision"] < m["revision"]:
                raise ManifestError("月の版が下がった: %s" % m["month"])
    old_files = files_of(old or {})
    added = []
    for path, f in files_of(new).items():
        before = old_files.get(path)
        if before is None:
            added.append(f)
        elif (before["sha256"], before["bytes"]) != (f["sha256"], f["bytes"]):
            raise ManifestError("公開済みのファイルが変わった: %s" % path)
    return added


def verify_download(base_url, f, opener=open_url, attempts=3, wait=10):
    """ファイルを取得してハッシュとサイズを確かめる。

    通信が途中で切れると短いファイルになるので、合わなければ取り直す。何度取っても
    合わないときだけ、配布元のファイルが違うとみなす。
    """
    for attempt in range(1, attempts + 1):
        digest = hashlib.sha256()
        size = 0
        try:
            with opener(base_url + f["path"], timeout=120) as response:
                for chunk in iter(lambda: response.read(1 << 20), b""):
                    digest.update(chunk)
                    size += len(chunk)
            if (digest.hexdigest(), size) == (f["sha256"], f["bytes"]):
                return
        except OSError as e:
            print("取得に失敗（%d/%d）: %s: %s" % (attempt, attempts, f["path"], e))
        if attempt < attempts:
            time.sleep(wait)
    raise ManifestError("配布元のファイルが manifest と合わない: %s" % f["path"])


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def write_json(path, value):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def check(target):
    """このリポジトリの索引に載っている全ファイルを取得し、ハッシュとサイズを確かめる。

    GitHub Actions が毎日、書き込まずに実行する。配布元のファイルが差し替えられたり
    消えたりしていれば失敗する。
    """
    root = read_json(os.path.join(target, "manifest.json"))
    if root is None:
        print("::error::manifest.json がありません")
        return 1
    count = 0
    try:
        validate_root(None, root)
        for r in root["regions"]:
            manifest = read_json(os.path.join(target, r["manifest"]))
            validate(None, manifest, r["region"])
            for f in files_of(manifest).values():
                verify_download(manifest["base_url"], f)
                count += 1
    except ManifestError as e:
        print("::error::%s" % e)
        return 1
    print("%d 件のファイルが索引と一致" % count)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="https://archive.epgdata.jp/")
    parser.add_argument("--target", default=".")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="書き込まず、索引に載っている全ファイルを確かめる")
    args = parser.parse_args()
    if args.check:
        return check(args.target)

    root_path = os.path.join(args.target, "manifest.json")
    try:
        root = fetch_json(args.source + "manifest.json")
        validate_root(read_json(root_path), root)
        updates = []
        for r in root["regions"]:
            path = os.path.join(args.target, r["manifest"])
            new = fetch_json(args.source + r["manifest"])
            added = validate(read_json(path), new, r["region"])
            if not args.skip_download:
                for f in added:
                    verify_download(new["base_url"], f)
            updates.append((path, new, len(added)))
    except ManifestError as e:
        print("::error::%s" % e)
        return 1

    write_json(root_path, root)
    for path, new, added in updates:
        write_json(path, new)
        print("%s: %d 件のファイルを追加" % (path, added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
