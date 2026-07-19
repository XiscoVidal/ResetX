"""Integración con Microsoft Activation Scripts (Massgrave / MAS)."""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
import threading

MAS_URL = "https://get.activated.win"
MAS_AIO_URL = (
    "https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/"
    "Microsoft-Activation-Scripts/items?path=/MAS/All-In-One-Version-KL/MAS_AIO.cmd&download=true"
)
MAS_AUTO_CMD = "& ([ScriptBlock]::Create((irm https://get.activated.win))) /HWID /Ohook /S"
MAS_AUTO_CMD_DOH = (
    "& ([ScriptBlock]::Create(("
    "curl.exe -s --doh-url https://1.1.1.1/dns-query https://get.activated.win | Out-String"
    "))) /HWID /Ohook /S"
)

CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


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
            "methods": [
                {
                    "id": "online",
                    "title": "Activación online (PowerShell)",
                    "desc": "Abre una ventana de PowerShell con el script oficial de MAS. Elige las opciones en verde del menú.",
                },
                {
                    "id": "online_doh",
                    "title": "Activación online (DNS alternativo)",
                    "desc": "Para cuando el ISP bloquea get.activated.win. Usa DNS over HTTPS (Cloudflare).",
                },
                {
                    "id": "aio_download",
                    "title": "Descargar MAS_AIO.cmd",
                    "desc": "Descarga el script All-In-One y lo ejecuta en una ventana nueva (útil si PowerShell online falla).",
                },
            ],
            "notes": [
                "El botón automático usa HWID (Windows) + Ohook (Office) en modo silencioso.",
                "Requiere ejecutar ResetX como administrador.",
                "Solo usa la URL oficial: https://get.activated.win",
            ],
        }

    def get_activation_status(self) -> dict:
        try:
            proc = subprocess.run(
                ["cscript", "//nologo", r"C:\Windows\System32\slmgr.vbs", "/xpr"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
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
        if self._job["running"]:
            return {"ok": False, "error": "Ya hay una operación MAS en curso"}
        if not self._is_admin():
            return {"ok": False, "error": "Ejecuta ResetX como administrador para activar Windows y Office."}

        self._job = self._idle_job()
        self._job["running"] = True

        def worker():
            proc = None
            try:
                self._job["logs"].append("[+] Descargando MAS desde get.activated.win …")
                self._job["logs"].append("[+] Activando Windows (HWID) + Office (Ohook) …")
                inner = MAS_AUTO_CMD_DOH if use_doh else MAS_AUTO_CMD
                ps_cmd = (
                    "[Net.ServicePointManager]::SecurityProtocol="
                    "[Net.SecurityProtocolType]::Tls12; "
                    + inner
                )
                proc = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=CREATE_NO_WINDOW,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    clean = line.rstrip()
                    if clean:
                        self._job["logs"].append(clean)
                proc.wait(timeout=900)
                if proc.returncode == 0:
                    self._job["logs"].append("[OK] Activación completada.")
                else:
                    self._job["logs"].append(f"[WARN] Código de salida: {proc.returncode}")
            except subprocess.TimeoutExpired:
                if proc:
                    proc.kill()
                self._job["error"] = "Tiempo de espera agotado (15 min)"
            except Exception as exc:
                self._job["error"] = str(exc)
                self._job["logs"].append(f"[ERROR] {exc}")
            finally:
                self._job["running"] = False
                self._job["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def launch(self, method: str = "online") -> dict:
        if self._job["running"]:
            return {"ok": False, "error": "Ya hay una operación MAS en curso"}

        self._job = self._idle_job()
        self._job["running"] = True

        def worker():
            try:
                if method == "online":
                    self._launch_online(use_doh=False)
                elif method == "online_doh":
                    self._launch_online(use_doh=True)
                elif method == "aio_download":
                    self._launch_aio()
                else:
                    raise ValueError(f"Método desconocido: {method}")
                self._job["logs"].append("Ventana de activación abierta. Sigue las instrucciones en verde.")
            except Exception as exc:
                self._job["error"] = str(exc)
                self._job["logs"].append(f"Error: {exc}")
            finally:
                self._job["running"] = False
                self._job["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def _launch_powershell_console(self, command: str):
        args = [
            "powershell.exe",
            "-NoExit",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command",
            (
                "[Net.ServicePointManager]::SecurityProtocol="
                "[Net.SecurityProtocolType]::Tls12; "
                f"{command}"
            ),
        ]
        subprocess.Popen(args, creationflags=CREATE_NEW_CONSOLE)

    def _launch_online(self, *, use_doh: bool):
        if use_doh:
            cmd = f"iex (curl.exe -s --doh-url https://1.1.1.1/dns-query {MAS_URL} | Out-String)"
        else:
            cmd = f"irm {MAS_URL} | iex"
        self._launch_powershell_console(cmd)

    def _launch_aio(self):
        fd, path = tempfile.mkstemp(suffix="_MAS_AIO.cmd")
        os.close(fd)
        try:
            import requests

            resp = requests.get(MAS_AIO_URL, timeout=60, headers={"User-Agent": "ResetX-MAS"})
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            subprocess.Popen(["cmd.exe", "/k", path], creationflags=CREATE_NEW_CONSOLE)
        except Exception:
            if os.path.exists(path):
                os.remove(path)
            raise
