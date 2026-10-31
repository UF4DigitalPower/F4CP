from __future__ import annotations

import hashlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.core.github_release import (
    DownloadCancelled, ReleaseAsset, ReleaseError, compatible_assets, download_asset,
    fetch_release, is_newer_version, repository_slug, validate_asset_name,
)


class Response(io.BytesIO):
    def __init__(self, data: bytes, headers=None):
        super().__init__(data)
        self.headers = headers or {}


def release_payload(tag="v2.1.0", prerelease=False, **extra):
    return {
        "tag_name": tag, "name": tag, "body": "Release notes", "draft": False,
        "prerelease": prerelease,
        "assets": [{
            "name": "F4CP-windows-x64.zip", "size": 7, "state": "uploaded",
            "browser_download_url": "https://github.com/UF4DigitalPower/F4CP/releases/download/v2.1.0/F4CP-windows-x64.zip",
            "digest": "sha256:" + "a" * 64,
        }], **extra,
    }


class VersionTests(unittest.TestCase):
    def test_numeric_order_and_prereleases(self):
        for remote, local, expected in [
            ("v2.0.10", "2.0.9", True), ("2.0.0", "2.0.0.RC1", True),
            ("2.0.0.B1", "2.0.0.A9", True), ("2.0.0.RC1", "2.0.0.B9", True),
            ("v1.1.0.RC1", "2.0.0.A1", False), ("v2.0.0", "2.0.0", False),
        ]:
            with self.subTest(remote=remote, local=local):
                self.assertEqual(is_newer_version(remote, local), expected)

    def test_bad_version_does_not_trigger_update(self):
        with self.assertRaises(ReleaseError):
            is_newer_version("nightly", "2.0.0")

    def test_supported_repository_urls(self):
        for url in [
            "https://github.com/UF4DigitalPower/F4CP", "https://github.com/UF4DigitalPower/F4CP.git",
            "https://github.com/UF4DigitalPower/F4CP/releases/latest",
            "https://api.github.com/repos/UF4DigitalPower/F4CP/releases/latest",
        ]:
            with self.subTest(url=url):
                self.assertEqual(repository_slug(url), "UF4DigitalPower/F4CP")

    def test_invalid_repository_urls(self):
        for url in ["http://github.com/a/b", "https://example.com/a/b", "https://github.com/a", "https://api.github.com/a/b"]:
            with self.subTest(url=url), self.assertRaises(ReleaseError):
                repository_slug(url)


class ReleaseTests(unittest.TestCase):
    def test_stable_release_and_digest(self):
        with patch("app.core.github_release.urlopen", return_value=Response(json.dumps(release_payload()).encode())) as open_mock:
            release = fetch_release("https://github.com/UF4DigitalPower/F4CP")
        request = open_mock.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/releases/latest"))
        self.assertEqual(release.tag, "v2.1.0")
        self.assertEqual(release.assets[0].sha256, "a" * 64)
        self.assertEqual(request.get_header("User-agent"), "F4CP-UpdateChecker")

    def test_prerelease_channel_uses_highest_version_and_ignores_drafts(self):
        payload = [release_payload("v2.1.0"), release_payload("v2.3.0.A1", True),
                   release_payload("v9.0.0", draft=True), release_payload("nightly")]
        with patch("app.core.github_release.urlopen", return_value=Response(json.dumps(payload).encode())):
            self.assertEqual(fetch_release("https://github.com/a/b", True).tag, "v2.3.0.A1")

    def test_no_releases_and_rate_limit(self):
        for status in (404, 403, 429):
            with self.subTest(status=status), patch("app.core.github_release.urlopen", side_effect=HTTPError("https://api.github.com", status, "error", {}, None)):
                with self.assertRaises(ReleaseError):
                    fetch_release("https://github.com/a/b")

    def test_invalid_responses(self):
        for payload in ["not json", "[]", '{"tag_name": "v2.0.0", "assets": null}',
                        json.dumps(release_payload(prerelease=True)), json.dumps(release_payload(draft=True))]:
            with self.subTest(payload=payload), patch("app.core.github_release.urlopen", return_value=Response(payload.encode())):
                with self.assertRaises(ReleaseError):
                    fetch_release("https://github.com/a/b")

    def test_untrusted_asset_url_is_not_offered(self):
        payload = release_payload()
        payload["assets"][0]["browser_download_url"] = "https://example.com/F4CP.zip"
        with patch("app.core.github_release.urlopen", return_value=Response(json.dumps(payload).encode())):
            self.assertEqual(fetch_release("https://github.com/UF4DigitalPower/F4CP").assets, ())


class AssetTests(unittest.TestCase):
    def assets(self, *names):
        return tuple(ReleaseAsset(name, "https://github.com/a/b/releases/download/v2/" + name) for name in names)

    def test_native_windows_x64_is_preferred(self):
        assets = self.assets("F4CP-windows-x86.zip", "F4CP-linux-x64.tar.gz", "F4CP-windows-arm64.zip", "F4CP-windows-x86_64.zip")
        self.assertEqual([a.name for a in compatible_assets(assets, "Windows", "AMD64")],
                         ["F4CP-windows-x86_64.zip", "F4CP-windows-x86.zip"])

    def test_windows_x86_and_arm_do_not_get_x64_packages(self):
        assets = self.assets("F4CP-windows-x64.zip", "F4CP-windows-x86.zip", "F4CP-windows-arm64.zip")
        self.assertEqual([a.name for a in compatible_assets(assets, "Windows", "x86")], ["F4CP-windows-x86.zip"])
        self.assertEqual([a.name for a in compatible_assets(assets, "Windows", "ARM64")], ["F4CP-windows-arm64.zip"])

    def test_firmware_sources_and_checksums_are_not_software_packages(self):
        self.assertEqual(compatible_assets(self.assets("firmware.bin", "F4CP-source.zip", "F4CP-symbols.zip", "sha256.txt"), "Windows", "AMD64"), [])

    def test_other_platforms(self):
        assets = self.assets("F4CP-macos-arm64.dmg", "F4CP-linux-aarch64.tar.gz", "F4CP-windows-x64.zip")
        self.assertEqual([a.name for a in compatible_assets(assets, "Darwin", "arm64")], ["F4CP-macos-arm64.dmg"])
        self.assertEqual([a.name for a in compatible_assets(assets, "Linux", "aarch64")], ["F4CP-linux-aarch64.tar.gz"])

    def test_unsafe_filenames(self):
        for name in ["../app.zip", r"..\app.zip", "C:app.zip", "NUL.zip", "file.zip ", "file.zip.", ""]:
            with self.subTest(name=name), self.assertRaises(ReleaseError):
                validate_asset_name(name)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "update.zip"
        self.data = b"a real release package" * 10_000
        self.asset = ReleaseAsset("F4CP.zip", "https://github.com/a/b/releases/download/v2/F4CP.zip",
                                  len(self.data), hashlib.sha256(self.data).hexdigest())

    def test_successful_atomic_download_with_progress(self):
        progress = []
        self.target.write_bytes(b"old file")
        with patch("app.core.github_release.urlopen", return_value=Response(self.data)):
            self.assertEqual(download_asset(self.asset, self.target, progress=lambda n, total: progress.append((n, total))), self.target)
        self.assertEqual(self.target.read_bytes(), self.data)
        self.assertEqual(progress[-1], (len(self.data), len(self.data)))
        self.assertEqual(list(self.target.parent.glob("*.part")), [])

    def test_truncated_and_corrupt_downloads_preserve_existing_file(self):
        for data in [self.data[:-1], b"X" * len(self.data), self.data + b"extra"]:
            self.target.write_bytes(b"existing")
            with self.subTest(size=len(data)), patch("app.core.github_release.urlopen", return_value=Response(data)):
                with self.assertRaises(ReleaseError):
                    download_asset(self.asset, self.target)
            self.assertEqual(self.target.read_bytes(), b"existing")
            self.assertEqual(list(self.target.parent.glob("*.part")), [])

    def test_cancel_during_download_removes_partial_file(self):
        cancel = threading.Event()
        def progress(downloaded, _):
            if downloaded:
                cancel.set()
        with patch("app.core.github_release.urlopen", return_value=Response(self.data)):
            with self.assertRaises(DownloadCancelled):
                download_asset(self.asset, self.target, cancel=cancel, progress=progress)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob("*.part")), [])

    def test_unknown_length(self):
        asset = ReleaseAsset(self.asset.name, self.asset.download_url)
        with patch("app.core.github_release.urlopen", return_value=Response(self.data)):
            download_asset(asset, self.target)
        self.assertEqual(self.target.read_bytes(), self.data)

    def test_network_failure(self):
        with patch("app.core.github_release.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(ReleaseError):
                download_asset(self.asset, self.target)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
