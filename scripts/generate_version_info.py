"""Genera build/version_info.txt para PyInstaller."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from version import __app_name__, __version__  # noqa: E402

parts = [int(x) for x in __version__.split(".")]
while len(parts) < 4:
    parts.append(0)
fv = tuple(parts[:4])

content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={fv},
    prodvers={fv},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040A04B0',
        [
          StringStruct('CompanyName', 'XiscoVidal'),
          StringStruct('FileDescription', '{__app_name__} - Optimizador Windows'),
          StringStruct('FileVersion', '{__version__}'),
          StringStruct('InternalName', '{__app_name__}'),
          StringStruct('LegalCopyright', 'Copyright (c) XiscoVidal'),
          StringStruct('OriginalFilename', 'ResetX.exe'),
          StringStruct('ProductName', '{__app_name__}'),
          StringStruct('ProductVersion', '{__version__}'),
        ])
    ]),
    VarFileInfo([VarStruct('Translation', [1034, 1200])])
  ]
)
"""

out_dir = os.path.join(ROOT, "build")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "version_info.txt")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)
print(out_path)
