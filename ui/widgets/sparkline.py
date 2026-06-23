"""High-performance sparkline with glassmorphism background."""
import tkinter as tk
from collections import deque
from ui import theme as T

HISTORY_LEN = 30


class Sparkline(tk.Canvas):
    def __init__(self, master, color=T.ACCENT, height=28, **kw):
        super().__init__(
            master, height=height, bg=T.SURFACE,
            highlightthickness=0, **kw,
        )
        self._color = color
        self._data = deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self._pending = False
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, _):
        if self._pending:
            return
        self._pending = True
        self.after(16, self._render)

    def push(self, value: float):
        self._data.append(max(0, min(100, value)))
        self._render()

    def _render(self):
        self._pending = False
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10:
            return
        data = list(self._data)
        if not data:
            return
        mx = max(data) or 1
        step = w / max(len(data) - 1, 1)
        pts = []
        for i, v in enumerate(data):
            x = i * step
            y = h - (v / mx) * (h - 4) - 2
            pts.extend([x, y])
        if len(pts) >= 4:
            self.create_line(pts, fill=self._color, width=2, smooth=True)
