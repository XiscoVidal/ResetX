"""Integración con Microsoft Activation Scripts (Massgrave / MAS).

IMPORTANTE: ResetX NO ejecuta scripts de activación en procesos ocultos.
Solo abre ventanas externas elevadas o muestra comandos para copiar.
Esto reduce falsos positivos de Windows Defender sobre ResetX.exe.
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
                "manual_hwid_ohook": (
                    "& ([ScriptBlock]::Create((irm https://get.activated.win))) /HWID /Ohook"
                ),
            },
            "methods": [
                {
                    "id": "online_console",
                    "title": "Abrir PowerShell (comando oficial)",
                    "desc": "Abre una ventana de PowerShell elevada con el comando oficial. En el menú elige opciones en verde.",
                },
                {
                    "id": "online_doh_console",
                    "title": "PowerShell con DNS alternativo",
                    "desc": "Si tu ISP bloquea get.activated.win. Usa Cloudflare DoH.",
                },
                {
                    "id": "aio_download",
                    "title": "Descargar MAS_AIO.cmd",
                    "desc": "Descarga el script a Descargas y lo abre en CMD elevado (sin ejecutar desde ResetX).",
                },
            ],
            "notes": [
                "Windows Defender puede alertar sobre scripts de activación — es un falso positivo habitual.",
                "ResetX NO ejecuta activación en segundo plano: siempre en ventana externa que tú controlas.",
                "Requiere administrador. URL oficial: https://get.activated.win",
                "Si Defender bloquea ResetX.exe, añade exclusión solo para la carpeta de instalación.",
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
        """Deprecated: redirige a consola externa (no ejecución embebida)."""
        method = "online_doh_console" if use_doh else "online_console"
        return self.launch(method)

    def launch(self, method: str = "online_console") -> dict:
        if self._job["running"]:
            return {"ok": False, "error": "Ya hay una operación MAS en curso"}

        self._job = self._idle_job()
        self._job["running"] = True

        def worker():
            try:
                if not self._is_admin():
                    self._job["logs"].append(
                        "[WARN] Ejecuta ResetX como administrador para que MAS funcione."
                    )
                if method == "online_console":
                    self._open_elevated_powershell(MAS_CMD_ONLINE)
                    self._job["logs"].append("Ventana PowerShell abierta. Pega el comando si no aparece y elige opciones verdes.")
                elif method == "online_doh_console":
                    self._open_elevated_powershell(MAS_CMD_DOH)
                    self._job["logs"].append("Ventana PowerShell (DoH) abierta.")
                elif method == "aio_download":
                    path = self._download_aio_to_downloads()
                    self._open_elevated_cmd(path)
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

    def _open_elevated_powershell(self, command: str):
        ps_inner = (
            "[Net.ServicePointManager]::SecurityProtocol="
            "[Net.SecurityProtocolType]::Tls12; "
            f'Write-Host "MAS — comando oficial. Elige opciones VERDES en el menu." -ForegroundColor Green; '
            f"Write-Host ''; Write-Host 'Comando:' -ForegroundColor Cyan; "
            f"Write-Host '{command}'; Write-Host ''; "
            f"Write-Host 'Ejecutando en 3 segundos... (Ctrl+C para cancelar)'; "
            f"Start-Sleep -Seconds 3; "
            f"{command}"
        )
        args = [
            "powershell.exe", "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-Command", ps_inner,
        ]
        self._run_elevated(args)

    def _open_elevated_cmd(self, script_path: str):
        args = ["cmd.exe", "/k", f'"{script_path}"']
        self._run_elevated(args)

    @staticmethod
    def _run_elevated(args: list[str]):
        if MasActivation._is_admin():
            subprocess.Popen(args, creationflags=CREATE_NEW_CONSOLE)
            return
        # UAC elevate
        params = " ".join(f'"{a}"' if " " in a else a for a in args[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", args[0], params or None, None, 1
        )

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
