"""Premium glassmorphism card with hover glow effect."""
import customtkinter as ctk
from ui import theme as T


class GlassCard(ctk.CTkFrame):
    def __init__(self, master, hover_glow=True, accent_color=None, **kw):
        defaults = dict(
            fg_color=T.SURFACE, border_color=T.BORDER,
            border_width=1, corner_radius=T.RADIUS_MD,
        )
        defaults.update(kw)
        super().__init__(master, **defaults)
        self._accent = accent_color or T.ACCENT
        self._default_border = T.BORDER
        if hover_glow:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        self.configure(border_color=self._accent)

    def _on_leave(self, _):
        self.configure(border_color=self._default_border)
