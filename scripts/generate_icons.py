"""Genera resetx.ico y resetx.png desde el diseño SVG (rasterizado con Pillow)."""
from __future__ import annotations

import os
import struct
import zlib

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
ACCENT = (59, 130, 246)
ACCENT_LIGHT = (96, 165, 250)
BG = (13, 17, 23)
SURFACE = (22, 27, 34)
BORDER = (48, 54, 61)


def _render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 32)
    radius = size // 4
    draw.rounded_rectangle((pad, pad, size - pad, size - pad), radius=radius, fill=BG)
    inner = pad + max(1, size // 32)
    draw.rounded_rectangle(
        (inner, inner, size - inner, size - inner),
        radius=max(4, radius - 4),
        fill=SURFACE,
        outline=BORDER,
        width=max(1, size // 64),
    )
    cx, cy = size // 2, size // 2
    stroke = max(3, size // 9)
    margin = size // 4
    draw.line((margin, margin, size - margin, size - margin), fill=ACCENT, width=stroke)
    draw.line((size - margin, margin, margin, size - margin), fill=ACCENT, width=stroke)
    dot = max(4, size // 14)
    draw.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=ACCENT_LIGHT)
    return img


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _write_ico(path: str, images: list[Image.Image]) -> None:
    entries = []
    offset = 6 + 16 * len(images)
    for img in images:
        rgba = img.convert("RGBA")
        w, h = rgba.size
        entries.append((w, h, offset))
        offset += 40 + w * h * 4

    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)))
        data_offset = 6 + 16 * len(images)
        blob = b""
        for img, (w, h, off) in zip(images, entries):
            f.write(struct.pack("<BBBBHHII", w if w < 256 else 0, h if h < 256 else 0, 0, 0, 1, 32, len(blob) + 40, data_offset + len(blob)))
            raw = img.convert("RGBA").tobytes("raw", "BGRA")
            blob += struct.pack("<IIIHHIIIIII", 40, w, h * 2, 1, 32, 0, len(raw), 0, 0, 0, 0)
            blob += raw
        f.write(blob)


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_render(s) for s in sizes]
    images[-1].save(os.path.join(ASSETS, "resetx.png"), "PNG")
    _write_ico(os.path.join(ASSETS, "resetx.ico"), images)
    print(f"Iconos generados en {ASSETS}")


if __name__ == "__main__":
    main()
