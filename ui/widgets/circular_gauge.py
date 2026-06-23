"""High-performance circular gauge with glassmorphism styling."""
import tkinter as tk
from ui import theme as T


class CircularGauge(tk.Canvas):
    def __init__(self, master, color=T.ACCENT, title="", **kw):
        super().__init__(
            master, width=1, height=1, bg=T.BG_SECONDARY,
            highlightthickness=0, **kw,
        )
        self._color = color
        self._title = title
        self._pct = -1
        self._pending = False
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if self._pending:
            return
        self._pending = True
        self.after(16, lambda: self._draw(event.width, event.height))

    def _draw(self, w, h):
        self._pending = False
        self.delete("all")
        if w < 20 or h < 20:
            return
        pad = int(min(w, h) * 0.12)
        s = min(w, h) - pad * 2
        t = max(6, s // 12)
        ox = (w - s) // 2
        oy = (h - s) // 2
        fp = max(13, int(s * 0.22))
        ft = max(8, int(s * 0.09))
        x1, y1 = ox + t, oy + t
        x2, y2 = ox + s - t, oy + s - t

        self.create_oval(x1, y1, x2, y2, outline=T.ELEVATED, width=t)
        if self._pct > 0:
            self.create_arc(
                x1, y1, x2, y2, start=90,
                extent=-(self._pct / 100) * 360,
                outline=self._color, width=t, style="arc",
            )

        cx, cy = w / 2, h / 2
        self.create_text(
            cx, cy - s * 0.05, text=f"{int(self._pct if self._pct >= 0 else 0)}%",
            fill=T.TEXT, font=("Segoe UI", fp, "bold"),
        )
        self.create_text(
            cx, cy + s * 0.18, text=self._title.upper(),
            fill=T.TEXT_SEC, font=("Segoe UI", ft, "bold"),
        )

    def draw_arc(self, percentage):
        self._pct = percentage
        w, h = self.winfo_width(), self.winfo_height()
        if w > 1 and h > 1:
            self._draw(w, h)
