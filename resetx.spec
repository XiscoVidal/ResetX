# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_dir = os.path.dirname(os.path.abspath(SPEC))

icon_file = os.path.join(project_dir, "assets", "resetx.ico")
version_file = os.path.join(project_dir, "build", "version_info.txt")

datas = [
    (os.path.join(project_dir, "assets"), "assets"),
    (os.path.join(project_dir, "webui"), "webui"),
    (os.path.join(project_dir, "data", "apps_database.json"), "data"),
    (os.path.join(project_dir, "backend", "LHM"), os.path.join("backend", "LHM")),
]
datas += collect_data_files("webview")

hiddenimports = [
    "clr_loader",
    "clr_loader.util",
    "clr_loader.ffi",
    "pythonnet",
    "version",
    "backend.api",
    "backend.update_manager",
]
hiddenimports += collect_submodules("webview")

a = Analysis(
    [os.path.join(project_dir, "main.py")],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "customtkinter", "PIL"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe_kwargs = dict(
    name="ResetX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=icon_file if os.path.exists(icon_file) else None,
)
if os.path.exists(version_file):
    exe_kwargs["version"] = version_file

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    **exe_kwargs,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ResetX",
)
