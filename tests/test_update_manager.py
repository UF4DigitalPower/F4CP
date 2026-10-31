from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QApplication

from app.core.github_release import DownloadCancelled, ReleaseAsset, ReleaseError, SoftwareRelease
from app.manager.manager_update import UpdateCheckFinishedEvent, UpdateManager


class Config:
    def __init__(self):
        for key, value in dict(appVersion="2.0.0.A1", latestAppVersion="", updateUrl="https://github.com/a/b",
                               includePrereleases=False, localLowerVersion="v1", latestLowerVersion="v2",
                               localUpperVersion="v3", latestUpperVersion="v4").items():
            setattr(self, key, SimpleNamespace(value=value))
        self.saved = []

    def set(self, item, value, save=False):
        item.value = value
        self.saved.append((value, save))


class Receiver(QObject):
    def __init__(self):
        super().__init__()
        self.result = None

    def event(self, event):
        if event.type() == UpdateCheckFinishedEvent.EVENT_TYPE:
            self.result = event.result
            return True
        return super().event(event)


class ManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.cfg = Config()
        self.manager = UpdateManager(SimpleNamespace(cfg=self.cfg))
        self.release = SoftwareRelease("v2.0.0", "F4CP", "notes", "https://github.com/a/b/releases/tag/v2.0.0", False,
                                       (ReleaseAsset("F4CP-windows-x64.zip", "https://github.com/a/b/releases/download/v2.0.0/F4CP.zip"),))

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Qt worker result was not delivered")

    def test_check_result_reaches_gui_signal_and_legacy_event(self):
        receiver = Receiver()
        results = []
        self.manager.checkFinished.connect(results.append)
        with patch("app.manager.manager_update.fetch_release", return_value=self.release):
            self.assertTrue(self.manager.check_for_updates(receiver))
            self.assertFalse(self.manager.check_for_updates(receiver))
            self.wait_until(lambda: receiver.result is not None)
        self.assertTrue(receiver.result.success)
        self.assertTrue(receiver.result.has_changes)
        self.assertEqual(results[0], receiver.result)
        self.assertEqual(self.cfg.latestAppVersion.value, "v2.0.0")
        self.assertEqual(self.cfg.appVersion.value, "2.0.0.A1")
        self.assertEqual(receiver.result.snapshot.local_lower_version, "v1")

    def test_failed_check_clears_stale_release(self):
        self.manager.latest_release = self.release
        results = []
        self.manager.checkFinished.connect(results.append)
        with patch("app.manager.manager_update.fetch_release", side_effect=ReleaseError("offline")):
            self.manager.check_for_updates()
            self.wait_until(lambda: bool(results))
        self.assertFalse(results[0].success)
        self.assertFalse(self.manager.is_checking)
        self.assertIsNone(self.manager.latest_release)

    def test_download_completion_does_not_change_installed_version(self):
        results = []
        self.manager.downloadFinished.connect(results.append)
        self.manager.latest_release = self.release
        target = Path(tempfile.gettempdir()) / "F4CP-manager-test.zip"
        with patch("app.manager.manager_update.download_asset", return_value=target):
            self.assertTrue(self.manager.download_update(self.release.assets[0], target))
            self.assertFalse(self.manager.check_for_updates())
            self.wait_until(lambda: bool(results))
        self.assertTrue(results[0].success)
        self.assertEqual(self.manager.last_download, target)
        self.assertFalse(self.manager.is_downloading)
        self.assertEqual(self.cfg.appVersion.value, "2.0.0.A1")

    def test_download_cancellation_allows_retry(self):
        results = []
        self.manager.downloadFinished.connect(results.append)
        self.manager.latest_release = self.release
        with patch("app.manager.manager_update.download_asset", side_effect=DownloadCancelled("cancelled")):
            self.assertTrue(self.manager.download_update(self.release.assets[0], Path("unused.zip")))
            self.wait_until(lambda: bool(results))
        self.assertTrue(results[0].cancelled)
        self.assertFalse(self.manager.is_downloading)
        self.assertIsNone(self.manager.last_download)

    def test_download_rejects_unmatched_asset(self):
        self.manager.latest_release = self.release
        asset = ReleaseAsset("F4CP-linux-x64.tar.gz", "https://github.com/a/b/releases/download/v2/F4CP.tar.gz")
        self.assertFalse(self.manager.download_update(asset, Path("unused.tar.gz")))


if __name__ == "__main__":
    unittest.main()
