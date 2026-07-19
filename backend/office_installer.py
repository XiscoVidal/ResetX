"""Instalación silenciosa de Microsoft 365 / Office C2R (Click-to-Run).

Usa el bootstrapper oficial de Microsoft (setup.exe) con XML de configuración,
sin depender de winget (que suele fallar con "No applicable installer found").
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time

OFFICE_SETUP_URL = "https://officecdn.microsoft.com/pr/wsus/setup.exe"
OFFICE_PRODUCT_ID = "O365ProPlusRetail"  # Microsoft 365 Apps

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

_OFFICE_PATHS = [
    r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
]


def is_office_installed() -> bool:
    for path in _OFFICE_PATHS:
        if os.path.isfile(path):
            return True
    try:
        import winreg

        for sub in (
            r"SOFTWARE\Microsoft\Office\ClickToRun\Configuration",
            r"SOFTWARE\WOW6432Node\Microsoft\Office\ClickToRun\Configuration",
        ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as key:
                    val, _ = winreg.QueryValueEx(key, "VersionToReport")
                    if val:
                        return True
            except OSError:
                pass
    except Exception:
        pass
    return False


def _write_config(config_path: str, product_id: str = OFFICE_PRODUCT_ID) -> None:
    xml = f"""<Configuration>
  <Add OfficeClientEdition="64" Channel="Current">
    <Product ID="{product_id}">
      <Language ID="MatchOS" />
    </Product>
  </Add>
  <Property Name="FORCEAPPSHUTDOWN" Value="TRUE" />
  <Display Level="None" AcceptEULA="TRUE" />
  <RemoveMSI All="TRUE" />
</Configuration>
"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(xml)


def install_office_c2r(
    on_log=None,
    *,
    cancel_check=None,
    timeout_sec: int = 1800,
    product_id: str = OFFICE_PRODUCT_ID,
) -> tuple[bool, str]:
    """Descarga setup.exe oficial, instala Office en silencio y espera a que termine."""
    cancel_check = cancel_check or (lambda: False)

    if is_office_installed():
        if on_log:
            on_log("  ✓ Office ya está instalado.")
        return True, "Office ya instalado"

    if on_log:
        on_log("  ↳ Instalación Office C2R (bootstrapper oficial Microsoft)…")
        on_log(f"  ✓ Producto: {product_id}")

    work_dir = tempfile.mkdtemp(prefix="resetx_office_")
    setup_path = os.path.join(work_dir, "setup.exe")
    config_path = os.path.join(work_dir, "config.xml")

    try:
        import requests

        if on_log:
            on_log(f"  ↳ Descargando {OFFICE_SETUP_URL}…")
        resp = requests.get(
            OFFICE_SETUP_URL,
            timeout=300,
            stream=True,
            headers={"User-Agent": "ResetX-Office"},
        )
        resp.raise_for_status()
        total = 0
        with open(setup_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                if cancel_check():
                    return False, "Cancelado"
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        if on_log:
            on_log(f"  ✓ Bootstrapper descargado ({total // 1024} KB)")

        _write_config(config_path, product_id)
        if on_log:
            on_log("  ↳ Ejecutando setup.exe /configure (instalación silenciosa, puede tardar varios minutos)…")

        proc = subprocess.run(
            [setup_path, "/configure", config_path],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=120,
        )
        if on_log:
            on_log(f"  ✓ Setup lanzado (código {proc.returncode})")
            if proc.stdout and proc.stdout.strip():
                on_log(f"    {proc.stdout.strip()[:200]}")
            if proc.returncode not in (0, 1707) and proc.stderr:
                on_log(f"    {proc.stderr.strip()[:200]}")

        if on_log:
            on_log("  ↳ Esperando a que Office termine de instalarse…")
        deadline = time.time() + timeout_sec
        last_ping = 0
        while time.time() < deadline:
            if cancel_check():
                return False, "Cancelado"
            if is_office_installed():
                if on_log:
                    on_log("  ✅ Office instalado correctamente.")
                return True, "Office instalado"
            now = time.time()
            if on_log and now - last_ping > 30:
                elapsed = int(now - (deadline - timeout_sec))
                on_log(f"    … aún instalando ({elapsed // 60} min)")
                last_ping = now
            time.sleep(5)

        return False, "Tiempo de espera agotado — Office no apareció instalado"
    except Exception as exc:
        if on_log:
            on_log(f"  ❌ Error instalando Office: {exc}")
        return False, str(exc)
