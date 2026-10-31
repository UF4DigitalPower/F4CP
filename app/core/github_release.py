# -*- coding: utf-8 -*-
# -------------------------------
#  @Project : F4CP
#  @Time    : 2026 - 10-31
#  @FileName: github_release.py
#  @FileType: GitHub 发布模块，负责 Release 查询、附件匹配和安全下载
#  @Software: PyCharm 2024.1.6 (Professional Edition)
#  @System  : Windows 11 23H2
#  @Author  : UF4
#  @Contact :
#  @Python  : 3.11
# -------------------------------

"""GitHub Release discovery and verified, atomic asset downloads (no Qt dependency)."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.version import Version, VersionError, parse_version as _parse_version


DEFAULT_REPOSITORY = "https://github.com/UF4DigitalPower/F4CP"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "F4CP-UpdateChecker",
    "X-GitHub-Api-Version": "2022-11-28",
}


class ReleaseError(Exception):
    """An update error that can be displayed directly to the user."""


class DownloadCancelled(ReleaseError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class SoftwareRelease:
    tag: str
    name: str
    notes: str
    url: str
    prerelease: bool
    assets: tuple[ReleaseAsset, ...]


def repository_slug(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "api.github.com"}:
        raise ReleaseError("请将软件更新地址配置为 HTTPS GitHub 仓库或 Release 地址。")
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname == "api.github.com":
        if not parts or parts.pop(0) != "repos":
            raise ReleaseError("GitHub API 地址必须包含 /repos/所有者/仓库。")
    if len(parts) < 2:
        raise ReleaseError("GitHub 更新地址缺少仓库所有者或仓库名。")
    owner, repo = parts[:2]
    repo = repo.removesuffix(".git")
    if not re.fullmatch(r"[\w.-]+", owner, re.ASCII) or not re.fullmatch(r"[\w.-]+", repo, re.ASCII):
        raise ReleaseError("GitHub 更新地址中的仓库名无效。")
    return f"{owner}/{repo}"


def parse_version(value: str) -> Version:
    try:
        return _parse_version(value)
    except VersionError as exc:
        raise ReleaseError(str(exc)) from exc


def is_newer_version(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def network_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code == 404:
            return "未找到可用的 Release，请确认仓库地址以及是否已发布版本。"
        if exc.code in {403, 429}:
            return "GitHub 请求被拒绝或已达到访问频率限制，请稍后重试。"
        return f"GitHub 请求失败（HTTP {exc.code}）。"
    if isinstance(exc, (URLError, TimeoutError, OSError)):
        return f"连接 GitHub 失败，请检查网络或系统代理：{exc}"
    return str(exc) or "更新操作失败，请稍后重试。"


def fetch_release(repository_url: str, include_prereleases: bool = False, timeout: float = 15) -> SoftwareRelease:
    slug = repository_slug(repository_url)
    endpoint = "releases?per_page=100" if include_prereleases else "releases/latest"
    request = Request(f"https://api.github.com/repos/{slug}/{endpoint}", headers=API_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(4 * 1024 * 1024).decode("utf-8-sig"))
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise ReleaseError(network_error(exc)) from exc

    if include_prereleases:
        if not isinstance(payload, list):
            raise ReleaseError("GitHub 返回了无效的 Release 列表。")
        releases = []
        for item in payload:
            if not isinstance(item, dict) or item.get("draft"):
                continue
            try:
                version = parse_version(str(item.get("tag_name", "")))
            except ReleaseError:
                continue
            releases.append((version, item))
        if not releases:
            raise ReleaseError("该仓库尚未发布可识别版本号的 Release。")
        payload = max(releases, key=lambda entry: entry[0])[1]

    if not isinstance(payload, dict) or not isinstance(payload.get("tag_name"), str):
        raise ReleaseError("GitHub 返回了无效的 Release 数据。")
    if payload.get("draft") or (payload.get("prerelease") and not include_prereleases):
        raise ReleaseError("当前没有可用的正式 Release。")
    parse_version(payload["tag_name"])
    raw_assets = payload.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ReleaseError("GitHub 返回了无效的 Release 附件列表。")
    assets = []
    for item in raw_assets:
        if not isinstance(item, dict) or item.get("state", "uploaded") != "uploaded":
            continue
        name, url = item.get("name"), item.get("browser_download_url")
        if not isinstance(name, str) or not isinstance(url, str):
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or not parsed.path.lower().startswith(f"/{slug}/releases/download/".lower()):
            continue
        digest = str(item.get("digest") or "")
        if digest and not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
            raise ReleaseError(f"发布文件 {name} 的 SHA-256 信息无效。")
        try:
            size = max(0, int(item.get("size", 0)))
        except (ValueError, TypeError):
            continue
        assets.append(ReleaseAsset(name, url, size, digest.removeprefix("sha256:").lower()))
    return SoftwareRelease(
        tag=payload["tag_name"],
        name=str(payload.get("name") or payload["tag_name"]),
        notes=str(payload.get("body") or ""),
        url=f"https://github.com/{slug}/releases/tag/{payload['tag_name']}",
        prerelease=bool(payload.get("prerelease")),
        assets=tuple(assets),
    )


def compatible_assets(assets: tuple[ReleaseAsset, ...], system: str | None = None,
                      machine: str | None = None) -> list[ReleaseAsset]:
    """Prefer native packages; Windows x64 can also run x86 packages."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "x64": "x64",
                    "i386": "x86", "i686": "x86", "x86": "x86",
                    "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)
    scored = []
    for asset in assets:
        name = asset.name.lower()
        if re.search(r"(?:^|[._-])(?:source|sources|symbols|debug|checksums?)(?:[._-]|$)", name):
            continue
        if not name.endswith((".zip", ".exe", ".msi", ".7z", ".tar.gz", ".tar.xz", ".appimage", ".dmg", ".pkg", ".deb", ".rpm")):
            continue
        tokens = set(re.split(r"[^a-z0-9]+", name))
        target_os = None
        if tokens & {"windows", "win", "win32", "win64"} or name.endswith((".exe", ".msi")):
            target_os = "windows"
        elif tokens & {"macos", "mac", "darwin", "osx"} or name.endswith((".dmg", ".pkg")):
            target_os = "darwin"
        elif "linux" in tokens or name.endswith((".appimage", ".deb", ".rpm")):
            target_os = "linux"
        if target_os is not None and target_os != system:
            continue
        target_arch = None
        if "x86_64" in name or tokens & {"x64", "amd64", "win64"}:
            target_arch = "x64"
        elif tokens & {"arm64", "aarch64"}:
            target_arch = "arm64"
        elif tokens & {"x86", "i386", "i686", "win32"}:
            target_arch = "x86"
        elif tokens & {"arm", "armv7", "armv7l", "armhf"}:
            target_arch = "arm"
        if target_arch and target_arch != architecture:
            if not (system == "windows" and architecture == "x64" and target_arch == "x86"):
                continue
            score = 40
        else:
            score = 100 if target_arch else 20
        score += 10 if target_os else 0
        score += 2 if name.endswith(".zip") else 0
        scored.append((score, asset))
    return [asset for _, asset in sorted(scored, key=lambda pair: (-pair[0], pair[1].name.lower()))]


def validate_asset_name(name: str) -> None:
    if (not name or name in {".", ".."} or re.search(r'[\\/:*?"<>|\x00-\x1f]', name)
            or name.rstrip(" .") != name
            or re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", name, re.IGNORECASE)):
        raise ReleaseError("Release 文件名无效，已停止下载。")


def download_asset(asset: ReleaseAsset, destination: Path, *, cancel: Event | None = None,
                   progress: Callable[[int, int], None] | None = None, timeout: float = 15) -> Path:
    """Keep partial data in the chosen directory and replace only after validation."""
    validate_asset_name(asset.name)
    parsed = urlparse(asset.download_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ReleaseError("仅支持 HTTPS GitHub Release 下载地址。")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial: Path | None = None
    try:
        if cancel and cancel.is_set():
            raise DownloadCancelled("下载已取消。")
        request = Request(asset.download_url, headers={"User-Agent": API_HEADERS["User-Agent"], "Accept": "application/octet-stream"})
        with urlopen(request, timeout=timeout) as response:
            total = asset.size or int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            digest = hashlib.sha256()
            last_report = 0.0
            with tempfile.NamedTemporaryFile(prefix=".f4cp-update-", suffix=".part", dir=destination.parent, delete=False) as output:
                partial = Path(output.name)
                if progress:
                    progress(0, total)
                while True:
                    if cancel and cancel.is_set():
                        raise DownloadCancelled("下载已取消。")
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if total and downloaded > total:
                        raise ReleaseError("下载文件大小与 Release 不一致，请重新检查更新。")
                    output.write(chunk)
                    digest.update(chunk)
                    now = time.monotonic()
                    if progress and now - last_report >= 0.1:
                        progress(downloaded, total)
                        last_report = now
            if total and downloaded != total:
                raise ReleaseError("文件下载不完整，请重试。")
            if downloaded == 0:
                raise ReleaseError("下载文件为空，请检查 Release 附件。")
            if asset.sha256 and digest.hexdigest() != asset.sha256:
                raise ReleaseError("SHA-256 校验失败，请重试下载。")
            if cancel and cancel.is_set():
                raise DownloadCancelled("下载已取消。")
            os.replace(partial, destination)
            if progress:
                progress(downloaded, total or downloaded)
            return destination
    except (HTTPError, URLError, OSError) as exc:
        raise ReleaseError(network_error(exc)) from exc
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
