"""Comprueba actualizaciones en GitHub Releases e instala en silencio."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
from typing import Callable, Optional

import requests

from version import GITHUB_RELEASES_API, INSTALLER_ASSET_NAME, __version__


def _parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _parse_version(remote) > _parse_version(local)


class UpdateManager:
    def __init__(self):
        self._checking = False

    def check_for_update(self, on_result: Callable[[Optional[dict]], None]) -> None:
        if self._checking:
            return
        self._checking = True

        def _worker():
            info = None
            try:
                resp = requests.get(
                    GITHUB_RELEASES_API,
                    timeout=12,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "ResetX-Updater"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tag = (data.get("tag_name") or "").lstrip("v")
                    if is_newer(tag, __version__):
                        url = None
                        for asset in data.get("assets", []):
                            if asset.get("name") == INSTALLER_ASSET_NAME:
                                url = asset.get("browser_download_url")
                                break
                        if url:
                            info = {
                                "version": tag,
                                "url": url,
                                "notes": (data.get("body") or "").strip()[:500],
                            }
            except Exception:
                pass
            finally:
                self._checking = False
                on_result(info)

        threading.Thread(target=_worker, daemon=True).start()

    def download_and_install(self, url: str, on_progress: Optional[Callable[[str], None]] = None) -> bool:
        try:
            if on_progress:
                on_progress("Descargando actualización…")
            resp = requests.get(url, timeout=120, stream=True)
            resp.raise_for_status()
            fd, path = tempfile.mkstemp(suffix="-ResetX-Setup.exe")
            os.close(fd)
            with open(path, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)
            if on_progress:
                on_progress("Instalando…")
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(
                [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                creationflags=flags,
            )
            return True
        except Exception as exc:
            if on_progress:
                on_progress(f"Error: {exc}")
            return False
