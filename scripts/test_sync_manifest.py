import hashlib
import io
import unittest

import sync_manifest as s

DATA = b"programmes"


def region(*months, name="tokyo"):
    return {"format_version": 1, "region": name, "name": "東京", "site": "https://tokyo.epgdata.jp/",
            "base_url": "https://archive.epgdata.jp/", "months": list(months)}


def month(name, revision=1, data=DATA, region_name="tokyo"):
    path = "%s/%s/epg-%s-%s.r%d.csv.zip" % (region_name, name[:4], region_name, name, revision)
    return {"month": name, "revision": revision, "generated_at": "x", "rows": {},
            "files": [{"format": "csv+zip", "path": path, "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}]}


def root(*names):
    return {"format_version": 1, "base_url": "https://archive.epgdata.jp/",
            "regions": [{"region": n, "name": n, "site": "https://%s.epgdata.jp/" % n,
                         "manifest": "%s/manifest.json" % n} for n in names]}


class RootTest(unittest.TestCase):
    def test_regions_can_be_added_but_not_removed(self):
        s.validate_root(None, root("tokyo"))
        s.validate_root(root("tokyo"), root("osaka", "tokyo"))
        with self.assertRaises(s.ManifestError):
            s.validate_root(root("osaka", "tokyo"), root("tokyo"))

    def test_bad_regions_are_rejected(self):
        for bad in (root("../x"), root("tokyo", "tokyo"), {"format_version": 1, "base_url": "https://a/"}):
            with self.assertRaises(s.ManifestError):
                s.validate_root(None, bad)
        moved = root("tokyo")
        moved["regions"][0]["manifest"] = "elsewhere.json"
        with self.assertRaises(s.ManifestError):
            s.validate_root(None, moved)


class RegionTest(unittest.TestCase):
    def test_first_manifest_and_new_month_are_accepted(self):
        self.assertEqual(len(s.validate(None, region(month("2026-08")), "tokyo")), 1)
        added = s.validate(region(month("2026-08")), region(month("2026-08"), month("2026-09")), "tokyo")
        self.assertEqual([f["path"] for f in added], ["tokyo/2026/epg-tokyo-2026-09.r1.csv.zip"])

    def test_changed_file_is_rejected(self):
        with self.assertRaises(s.ManifestError):
            s.validate(region(month("2026-08")), region(month("2026-08", data=b"other")), "tokyo")

    def test_new_revision_with_new_name_is_accepted(self):
        added = s.validate(region(month("2026-08")), region(month("2026-08", 2, b"fixed")), "tokyo")
        self.assertEqual([f["path"] for f in added], ["tokyo/2026/epg-tokyo-2026-08.r2.csv.zip"])

    def test_removed_month_and_lower_revision_are_rejected(self):
        with self.assertRaises(s.ManifestError):
            s.validate(region(month("2026-08")), region(), "tokyo")
        with self.assertRaises(s.ManifestError):
            s.validate(region(month("2026-08", 2)), region(month("2026-08", 1)), "tokyo")

    def test_paths_must_match_region_month_and_revision(self):
        for bad in (
            region(month("2026-08", region_name="osaka")),          # 別の地域のファイル
            region(month("2026-08"), name="osaka"),                   # 索引の地域が違う
        ):
            with self.assertRaises(s.ManifestError):
                s.validate(None, bad, "tokyo")
        traversal = region(month("2026-08"))
        traversal["months"][0]["files"][0]["path"] = "../etc/passwd"
        with self.assertRaises(s.ManifestError):
            s.validate(None, traversal, "tokyo")
        wrong_revision = region(month("2026-08"))
        wrong_revision["months"][0]["revision"] = 2
        with self.assertRaises(s.ManifestError):
            s.validate(None, wrong_revision, "tokyo")
        insecure = region(month("2026-08"))
        insecure["base_url"] = "http://archive.epgdata.jp/"
        with self.assertRaises(s.ManifestError):
            s.validate(None, insecure, "tokyo")


class DownloadTest(unittest.TestCase):
    def test_download_must_match_the_hash(self):
        f = month("2026-08")["files"][0]
        s.verify_download("https://archive.epgdata.jp/", f, opener=lambda url, timeout: io.BytesIO(DATA))
        with self.assertRaises(s.ManifestError):
            s.verify_download("https://archive.epgdata.jp/", f, wait=0,
                              opener=lambda url, timeout: io.BytesIO(b"tampered"))

    def test_a_cut_transfer_is_retried(self):
        f = month("2026-08")["files"][0]
        replies = [io.BytesIO(DATA[:3]), io.BytesIO(DATA)]
        s.verify_download("https://archive.epgdata.jp/", f, wait=0,
                          opener=lambda url, timeout: replies.pop(0))
        self.assertEqual(replies, [])


if __name__ == "__main__":
    unittest.main()
