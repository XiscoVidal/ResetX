"""ResetX — Premium glassmorphism System Optimizer & Software Hub."""
import os
import sys
import customtkinter as ctk

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ui import theme as T

T.init_theme()

from ui.app_window import AppWindow
from backend.utils import apply_window_icon
from version import __version__


class SplashScreen(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ResetX")
        self.geometry("420x240")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_PRIMARY)
        self.overrideredirect(True)
        apply_window_icon(self)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"420x240+{(sw - 420) // 2}+{(sh - 240) // 2}")
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(expand=True)
        ctk.CTkLabel(main, text="ResetX", font=T.font(38, "bold"), text_color=T.ACCENT).pack(pady=(10, 2))
        ctk.CTkLabel(main, text="Ultimate Optimizer & Hub", font=T.font(13), text_color=T.TEXT_SEC).pack()
        ctk.CTkLabel(main, text=f"v{__version__}", font=T.font(10), text_color=T.TEXT_MUTED).pack(pady=(2, 12))
        self._p = ctk.CTkProgressBar(main, width=280, progress_color=T.ACCENT, fg_color=T.ELEVATED)
        self._p.pack(pady=8)
        self._p.set(0.3)
        self.after(300, self._finish)

    def _finish(self):
        self._p.set(1.0)
        self.after(120, self.destroy)


if __name__ == "__main__":
    SplashScreen().mainloop()
    AppWindow().mainloop()
