"""Integración con Microsoft Activation Scripts (Massgrave / MAS).

Ejecuta activación en segundo plano (sin ventanas visibles) escribiendo scripts
temporales y usando CREATE_NO_WINDOW / PowerShell -WindowStyle Hidden.
El progreso se registra en archivos de log leídos por la UI de ResetX.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import tempfile
import threading
import time

MAS_URL = "https://get.activated.win"
MAS_CMD_ONLINE = f"irm {MAS_URL} | iex"
MAS_CMD_DOH = f"iex (curl.exe -s --doh-url https://1.1.1.1/dns-query {MAS_URL} | Out-String)"
MAS_AIO_URL = (
    "https://dev.azure.com/massgrave/Microsoft-Activation-Scripts/_apis/git/repositories/"
    "Microsoft-Activation-Scripts/items?path=/MAS/All-In-One-Version-KL/MAS_AIO.cmd&download=true"
)

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
SW_HIDE = 0

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

    @staticmethod
    def _log_path(name: str) -> str:
        return os.path.join(tempfile.gettempdir(), f"resetx_mas_{name}.log")

    def get_info(self) -> dict:
        office = self._detect_office()
        return {
            "url": MAS_URL,
            "docs": "https://massgrave.dev/",
            "github": "https://github.com/massgravel/Microsoft-Activation-Scripts",
            "admin": self._is_admin(),
            "office_installed": office["installed"],
            "office_detail": office["detail"],
            "commands": {
                "online": MAS_CMD_ONLINE,
                "online_doh": MAS_CMD_DOH,
                "windows": "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /HWID /S",
                "office": "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /Ohook /S",
            },
            "methods": [
                {
                    "id": "online_doh_console",
                    "title": "PowerShell con DNS alternativo",
                    "desc": "Si tu ISP bloquea get.activated.win. Usa Cloudflare DoH.",
                },
                {
                    "id": "aio_download",
                    "title": "Descargar MAS_AIO.cmd",
                    "desc": "Descarga el script a Descargas para uso manual.",
                },
            ],
            "notes": [
                "La activación se ejecuta en segundo plano — el progreso aparece en el registro de abajo.",
                "Activar Office: instala Microsoft 365 si no lo detecta, luego activa con Ohook.",
                "Recomendado: ejecutar ResetX como administrador.",
                "URL oficial: https://get.activated.win",
            ],
        }

    @staticmethod
    def _detect_office() -> dict:
        from backend.office_installer import is_office_installed

        if is_office_installed():
            for path in (
                r"C:\Program Files\Microsoft Office\root\Office16",
                r"C:\Program Files (x86)\Microsoft Office\root\Office16",
            ):
                if os.path.isdir(path):
                    return {"installed": True, "detail": path}
            return {"installed": True, "detail": "Microsoft Office"}
        return {"installed": False, "detail": "No detectado"}

    def get_activation_status(self) -> dict:
        try:
            proc = subprocess.run(
                ["cscript", "//nologo", r"C:\Windows\System32\slmgr.vbs", "/xpr"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=20,
            )
            raw = (proc.stdout or proc.stderr or "").strip()
            lower = raw.lower()
            licensed = "permanent" in lower or "permanente" in lower
            trial = "expira" in lower or "expires" in lower or "expiración" in lower

            edition = "Windows"
            m = re.search(r"Windows\s*\([^)]+\)\s*,?\s*([^:]+):", raw, re.I)
            if m:
                edition = m.group(1).strip()
            elif re.search(r"core edition", lower):
                edition = "Core"

            if licensed:
                headline = "Windows activado permanentemente"
                sub = f"Edición {edition} · licencia digital válida"
            elif trial:
                headline = "Windows en periodo de prueba"
                sub = raw
            else:
                headline = "Windows no activado"
                sub = raw or "No se pudo determinar el estado de la licencia."

            return {
                "ok": True,
                "text": raw or "No se pudo leer el estado.",
                "licensed": licensed,
                "trial": trial,
                "headline": headline,
                "sub": sub,
                "edition": edition,
            }
        except Exception as exc:
            return {
                "ok": False,
                "text": str(exc),
                "licensed": False,
                "trial": False,
                "headline": "Error al comprobar licencia",
                "sub": str(exc),
                "edition": "",
            }

    def get_job(self) -> dict:
        return self._job

    def auto_activate(self, use_doh: bool = False) -> dict:
        return self.launch("activate_windows")

    def launch(self, method: str = "activate_windows") -> dict:
        if self._job["running"]:
            return {"ok": False, "error": "Ya hay una operación MAS en curso"}

        self._job = self._idle_job()
        self._job["running"] = True

        def worker():
            log_file = None
            try:
                if method == "activate_windows":
                    log_file = self._log_path("windows")
                    ps1 = self._write_activation_ps1(
                        "windows",
                        log_file,
                        "Activación Windows (HWID)",
                        "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /HWID /S",
                    )
                    self._job["logs"].append("Activando Windows en segundo plano…")
                    self._launch_hidden_ps1(ps1)
                elif method == "activate_office":
                    log_file = self._log_path("office")
                    office = self._detect_office()
                    if office["installed"]:
                        self._job["logs"].append("Office detectado — activando Ohook…")
                        ps1 = self._write_activation_ps1(
                            "office",
                            log_file,
                            "Activación Office (Ohook)",
                            "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /Ohook /S",
                        )
                        self._launch_hidden_ps1(ps1)
                    else:
                        self._job["logs"].append(
                            "Office no detectado — instalando Microsoft 365 (instalador oficial)…"
                        )
                        from backend.office_installer import install_office_c2r

                        def _log(msg):
                            self._job["logs"].append(msg)

                        ok, msg = install_office_c2r(_log, timeout_sec=1800)
                        if not ok:
                            raise RuntimeError(msg or "No se pudo instalar Office")
                        self._job["logs"].append("Office instalado — activando con MAS /Ohook…")
                        ps1 = self._write_activation_ps1(
                            "office",
                            log_file,
                            "Activación Office (Ohook)",
                            "& ([ScriptBlock]::Create((irm https://get.activated.win -UseBasicParsing))) /Ohook /S",
                        )
                        self._launch_hidden_ps1(ps1)
                elif method == "online_doh_console":
                    log_file = self._log_path("doh")
                    ps1 = self._write_activation_ps1(
                        "doh",
                        log_file,
                        "MAS con DNS alternativo",
                        MAS_CMD_DOH,
                    )
                    self._job["logs"].append("Ejecutando MAS (DoH) en segundo plano…")
                    self._launch_hidden_ps1(ps1)
                elif method == "online_console":
                    log_file = self._log_path("menu")
                    ps1 = self._write_activation_ps1(
                        "menu",
                        log_file,
                        "MAS menú completo",
                        MAS_CMD_ONLINE,
                    )
                    self._launch_hidden_ps1(ps1)
                elif method == "aio_download":
                    path = self._download_aio_to_downloads()
                    self._job["logs"].append(f"MAS_AIO.cmd descargado en: {path}")
                    os.startfile(path)
                else:
                    raise ValueError(f"Método desconocido: {method}")

                if log_file:
                    self._tail_log(log_file, timeout=900 if method == "activate_office" else 600)
                    self._job["logs"].append("Proceso MAS finalizado. Comprueba el estado arriba.")
            except Exception as exc:
                self._job["error"] = str(exc)
                self._job["logs"].append(f"[ERROR] {exc}")
            finally:
                self._job["running"] = False
                self._job["done"] = True

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    @staticmethod
    def _write_activation_ps1(name: str, log_file: str, title: str, mas_command: str) -> str:
        content = f"""# ResetX — {title}
$log = '{log_file.replace("'", "''")}'
function Log($m) {{ "$(Get-Date -Format 'HH:mm:ss') $m" | Add-Content -Path $log -Encoding UTF8 }}
$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Log 'Iniciando: {title}'
try {{
    {mas_command}
    Log 'Completado correctamente.'
}} catch {{
    Log ('ERROR: ' + $_.Exception.Message)
}}
"""
        path = os.path.join(tempfile.gettempdir(), f"resetx_mas_{name}.ps1")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            open(log_file, "w", encoding="utf-8").close()
        except OSError:
            pass
        return path

    def _tail_log(self, log_file: str, timeout: int = 600):
        """Lee el log del script MAS hasta que el proceso termine o expire."""
        seen = 0
        deadline = time.time() + timeout
        proc_gone = False
        while time.time() < deadline and not proc_gone:
            if os.path.isfile(log_file):
                try:
                    with open(log_file, encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    for line in lines[seen:]:
                        clean = line.strip()
                        if clean:
                            self._job["logs"].append(clean)
                    seen = len(lines)
                    if lines and any("Completado" in l or "ERROR" in l for l in lines[-3:]):
                        break
                except OSError:
                    pass
            time.sleep(1.2)
            if seen > 0 and time.time() > deadline - 30:
                proc_gone = True

    def _launch_hidden_ps1(self, ps1_path: str):
        args = [
            "powershell.exe",
            "-WindowStyle", "Hidden",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", ps1_path,
        ]
        if self._is_admin():
            subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)
            return
        params = (
            f'-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File "{ps1_path}"'
        )
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", params, None, SW_HIDE
        )
        if ret <= 32:
            msg = _SHELL_ERRORS.get(ret, f"código {ret}")
            raise OSError(f"No se pudo iniciar PowerShell: {msg}")

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
