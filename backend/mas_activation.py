"""Integración con Microsoft Activation Scripts (Massgrave / MAS).

ResetX NO ejecuta activación embebida: escribe un .ps1 temporal y abre
PowerShell externo con ShellExecuteW (sin Popen elevado que provoca WinError 5).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
import threading

MAS_URL = "https://get.activated.win"
MAS_CMD_ONLINE = f"irm {MAS_URL} | iex"
MAS_CMD_DOH = f"iex (curl.exe -s --doh-url https://1.1.1.1/dns-query {MAS_URL} | Out-String)"
MAS_AIO_URL = (
    "https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/"
    "Microsoft-Activation-Scripts/items?path=/MAS/All-In-One-Version-KL/MAS_AIO.cmd&download=true"
)

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

_SHELL_ERRORS = {
    2: "archivo no encontrado",
    5: "acceso denegado — ejecuta ResetX como administrador",
    1223: "cancelado (UAC)",
}


class MasActivation:
    def __init__(self):
        self._job = self._idle_job()

    @staticmethod
    def _idle_job() -> dict:
        return {"running": False, "done": False, "logs": [], "error": None}

    @staticmethod
    def _is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def get_info(self) -> dict:
        return {
            "url": MAS_URL,
            "docs": "https://massgrave.dev/",
            "github": "https://github.com/massgravel/Microsoft-Activation-Scripts",
            "admin": self._is_admin(),
            "commands": {
                "online": MAS_CMD_ONLINE,
                "online_doh": MAS_CMD_DOH,
                "windows": "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /HWID",
                "office": "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /Ohook",
            },
            "methods": [
                {
                    "id": "activate_windows",
                    "title": "Activar Windows",
                    "desc": "Abre PowerShell externo y ejecuta MAS con /HWID (activación digital).",
                },
                {
                    "id": "activate_office",
                    "title": "Activar Office",
                    "desc": "Abre PowerShell externo y ejecuta MAS con /Ohook (Office 2016+).",
                },
                {
                    "id": "online_doh_console",
                    "title": "PowerShell con DNS alternativo",
                    "desc": "Si tu ISP bloquea get.activated.win. Usa Cloudflare DoH.",
                },
                {
                    "id": "aio_download",
                    "title": "Descargar MAS_AIO.cmd",
                    "desc": "Descarga el script a Descargas y lo abre en CMD (menú manual).",
                },
            ],
            "notes": [
                "ResetX solo abre ventanas externas — no ejecuta activación dentro de la app.",
                "Windows Defender puede alertar sobre scripts de activación (falso positivo habitual).",
                "Recomendado: ejecutar ResetX como administrador antes de activar.",
                "URL oficial: https://get.activated.win",
            ],
        }

    def get_activation_status(self) -> dict:
        try:
            proc = subprocess.run(
                ["cscript", "//nologo", r"C:\Windows\System32\slmgr.vbs", "/xpr"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=20,
            )
            text = (proc.stdout or proc.stderr or "").strip()
            licensed = "permanent" in text.lower() or "permanente" in text.lower()
            trial = "expira" in text.lower() or "expires" in text.lower()
            return {"ok": True, "text": text or "No se pudo leer el estado.", "licensed": licensed, "trial": trial}
        except Exception as exc:
            return {"ok": False, "text": str(exc), "licensed": False, "trial": False}

    def get_job(self) -> dict:
        return self._job

    def auto_activate(self, use_doh: bool = False) -> dict:
        method = "online_doh_console" if use_doh else "activate_windows"
        return self.launch(method)

    def launch(self, method: str = "activate_windows") -> dict:
        if self._job["running"]:
            return {"ok": False, "error": "Ya hay una operación MAS en curso"}

        self._job = self._idle_job()
        self._job["running"] = True

        def worker():
            try:
                if method == "activate_windows":
                    self._launch_mas_script(
                        "windows",
                        "Activar Windows (MAS /HWID)",
                        "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /HWID",
                    )
                    self._job["logs"].append("Ventana PowerShell abierta — activación Windows en curso.")
                elif method == "activate_office":
                    self._launch_mas_script(
                        "office",
                        "Activar Office (MAS /Ohook)",
                        "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /Ohook",
                    )
                    self._job["logs"].append("Ventana PowerShell abierta — activación Office en curso.")
                elif method == "online_console":
                    self._launch_mas_script(
                        "menu",
                        "MAS — menú completo",
                        MAS_CMD_ONLINE,
                    )
                    self._job["logs"].append("Ventana PowerShell abierta. Elige opciones VERDES en el menú.")
                elif method == "online_doh_console":
                    self._launch_mas_script("doh", "MAS con DNS alternativo", MAS_CMD_DOH)
                    self._job["logs"].append("Ventana PowerShell (DoH) abierta.")
                elif method == "aio_download":
                    path = self._download_aio_to_downloads()
                    self._open_executable("cmd.exe", f'/k "{path}"')
                    self._job["logs"].append(f"MAS_AIO.cmd descargado en: {path}")
                    self._job["logs"].append("Ventana CMD abierta — elige opciones verdes en el menú.")
                else:
                    raise ValueError(f"Método desconocido: {method}")
            except Exception as exc:
                self._job["error"] = str(exc)
                self._job["logs"].append(f"[ERROR] {exc}")
            finally:
                self._job["running"] = False
                self._job["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    @staticmethod
    def _write_ps1(name: str, title: str, mas_command: str) -> str:
        content = f"""# ResetX — {title}
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Write-Host ''
Write-Host '=== {title} ===' -ForegroundColor Green
Write-Host 'Script oficial MAS (get.activated.win)' -ForegroundColor Cyan
Write-Host ''
try {{
    {mas_command}
}} catch {{
    Write-Host ''
    Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red
}}
Write-Host ''
Write-Host 'Pulsa Enter para cerrar.' -ForegroundColor DarkGray
Read-Host
"""
        path = os.path.join(tempfile.gettempdir(), f"resetx_mas_{name}.ps1")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _launch_mas_script(self, name: str, title: str, mas_command: str):
        ps1 = self._write_ps1(name, title, mas_command)
        params = f'-NoExit -NoProfile -ExecutionPolicy Bypass -File "{ps1}"'
        self._open_executable("powershell.exe", params)

    @staticmethod
    def _open_executable(executable: str, parameters: str):
        """Abre un proceso visible. Usa 'open' si ya somos admin; 'runas' si no."""
        elevate = not MasActivation._is_admin()
        verb = "runas" if elevate else "open"
        ret = ctypes.windll.shell32.ShellExecuteW(None, verb, executable, parameters, None, 1)
        if ret <= 32:
            msg = _SHELL_ERRORS.get(ret, f"código {ret}")
            raise OSError(f"No se pudo abrir {executable}: {msg}")

    @staticmethod
    def _download_aio_to_downloads() -> str:
        import requests

        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads, exist_ok=True)
        path = os.path.join(downloads, "MAS_AIO.cmd")
        resp = requests.get(MAS_AIO_URL, timeout=90, headers={"User-Agent": "ResetX-MAS"})
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
