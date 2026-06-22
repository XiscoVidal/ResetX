import os
import sys
import customtkinter as ctk

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui import theme as T
T.init_theme()

from ui.app_window import AppWindow, __version__

BG = T.BG
ACCENT = T.ACCENT
TEXT_SEC = T.TEXT_SEC


class SplashScreen(ctk.CTk):
    """Splash ligero — no bloquea con I/O pesado."""

    def __init__(self):
        super().__init__()
        self.title("ResetX")
        self.geometry("400x220")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.overrideredirect(True)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"400x220+{(sw - 400) // 2}+{(sh - 220) // 2}")

        ctk.CTkLabel(self, text="ResetX", font=T.font(36, "bold"), text_color=ACCENT).pack(pady=(44, 4))
        ctk.CTkLabel(self, text="Ultimate Optimizer & Hub", font=T.font(13), text_color=TEXT_SEC).pack()
        ctk.CTkLabel(self, text=f"v{__version__}", font=T.font(10), text_color=T.TEXT_MUTED).pack(pady=(4, 16))

        self.progress = ctk.CTkProgressBar(self, width=260, progress_color=ACCENT, fg_color=T.ELEVATED)
        self.progress.pack(pady=8)
        self.progress.set(0.3)
        self.after(400, self._finish)

    def _finish(self):
        self.progress.set(1.0)
        self.after(150, self.destroy)


if __name__ == "__main__":
    splash = SplashScreen()
    splash.mainloop()
    AppWindow().mainloop()
