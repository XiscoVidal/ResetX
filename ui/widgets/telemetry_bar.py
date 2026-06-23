"""Glassmorphism telemetry progress bar."""
import customtkinter as ctk
from ui import theme as T


class TelemetryBar(ctk.CTkFrame):
    def __init__(self, master, title, color=T.ACCENT):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(1, weight=1)
        self._tl = ctk.CTkLabel(
            self, text=title, font=T.font(12, "bold"),
            text_color=T.TEXT_SEC, width=105, anchor="w",
        )
        self._tl.grid(row=0, column=0, sticky="w", padx=(0, 15))
        self._bar = ctk.CTkProgressBar(
            self, height=6, progress_color=color,
            fg_color=T.ELEVATED, corner_radius=3,
        )
        self._bar.grid(row=0, column=1, sticky="ew", padx=(0, 15))
        self._bar.set(0)
        self._vl = ctk.CTkLabel(
            self, text="0.0", font=T.font(13, "bold", mono=True),
            text_color=T.TEXT, width=95, anchor="e",
        )
        self._vl.grid(row=0, column=2, sticky="e")
        self._color = color

    def update_bar(self, pct, text):
        self._bar.set(pct)
        self._vl.configure(text=text)
