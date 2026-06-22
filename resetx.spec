# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_dir = os.path.dirname(os.path.abspath(SPEC))

icon_file = os.path.join(project_dir, "assets", "icons", "cpu.png")

datas = [
    (os.path.join(project_dir, "assets"), "assets"),
    (os.path.join(project_dir, "data", "apps_database.json"), "data"),
    (os.path.join(project_dir, "backend", "LHM"), os.path.join("backend", "LHM")),
]
datas += collect_data_files("customtkinter")

for locale in ("de", "es", "fr", "it", "ja", "pl", "ru", "sv", "tr", "zh-CN", "zh-Hant"):
    locale_dir = os.path.join(project_dir, "backend", locale)
    if os.path.isdir(locale_dir):
        datas.append((locale_dir, os.path.join("backend", locale)))

hiddenimports = [
    "PIL._tkinter_finder",
    "clr_loader",
    "clr_loader.util",
    "clr_loader.ffi",
    "pythonnet",
]
hiddenimports += collect_submodules("clr")

a = Analysis(
    [os.path.join(project_dir, "main.py")],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ResetX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=icon_file if os.path.exists(icon_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ResetX",
)
