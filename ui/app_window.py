import os
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from ui.views.dashboard_view import DashboardView
from ui.views.optimizer_view import OptimizerView
from ui.views.hub_view import HubView
from backend.icon_manager import IconManager
from backend.winget_manager import WingetManager
from backend.optimization_engine import OptimizationEngine
from backend.utils import get_base_path
from ui import theme as T

__version__ = "1.2.1"
_logo_image = None


def _create_logo_image(size=(150, 44)):
    global _logo_image
    if _logo_image is not None:
        return _logo_image
    logo_path = os.path.join(get_base_path(), "assets", "logo.png")
    if os.path.exists(logo_path):
        img = Image.open(logo_path)
        _logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        return _logo_image
    img = Image.new("RGBA", (300, 88), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    draw.text((8, 18), "Reset", fill=T.TEXT, font=font)
    draw.text((128, 18), "X", fill=T.ACCENT, font=font)
    _logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
    return _logo_image


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ResetX")
        self.minsize(900, 600)
        self.configure(fg_color=T.BG)

        icon_path = os.path.join(get_base_path(), "assets", "icons", "cpu.png")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(default=icon_path)
            except Exception:
                pass

        self._build_sidebar()
        self._build_views()
        self._current_view = None
        self.show_dashboard()

        self.after(50, self._maximize)
        self.after(8000, self._refresh_sidebar_counts)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _maximize(self):
        try:
            self.state("zoomed")
        except Exception:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")

    def _build_sidebar(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=T.SURFACE)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="", image=_create_logo_image())
        self.logo_label.grid(row=0, column=0, padx=T.PAD_MD, pady=(T.PAD_LG, T.PAD_SM))

        self._sep1 = T.separator(self.sidebar_frame)
        self._sep1.grid(row=1, column=0, sticky="ew", padx=T.PAD_MD, pady=(4, 12))

        self.btn_dashboard = self._nav_button("Dashboard", self.show_dashboard)
        self.btn_dashboard.grid(row=2, column=0, padx=12, pady=3, sticky="ew")
        self.btn_optimizer = self._nav_button("Rendimiento", self.show_optimizer)
        self.btn_optimizer.grid(row=3, column=0, padx=12, pady=3, sticky="ew")
        self.btn_hub = self._nav_button("Software Hub", self.show_hub)
        self.btn_hub.grid(row=4, column=0, padx=12, pady=3, sticky="ew")

        self._sep2 = T.separator(self.sidebar_frame)
        self._sep2.grid(row=5, column=0, sticky="ew", padx=T.PAD_MD, pady=12)

        self.tweak_count_lbl = ctk.CTkLabel(
            self.sidebar_frame, text=f"{OptimizationEngine.count_available_tweaks()} tweaks disponibles",
            font=T.font(11), text_color=T.TEXT_MUTED, anchor="w",
        )
        self.tweak_count_lbl.grid(row=6, column=0, padx=T.PAD_MD, sticky="ew")
        self.updates_count_lbl = ctk.CTkLabel(
            self.sidebar_frame, text="0 actualizaciones",
            font=T.font(11), text_color=T.TEXT_MUTED, anchor="w",
        )
        self.updates_count_lbl.grid(row=7, column=0, padx=T.PAD_MD, pady=(2, 0), sticky="ew")

        self.version_lbl = ctk.CTkLabel(
            self.sidebar_frame, text=f"v{__version__}",
            font=T.font(10), text_color=T.TEXT_MUTED,
        )
        self.version_lbl.grid(row=9, column=0, padx=T.PAD_MD, pady=(0, T.PAD_MD), sticky="w")

    def _build_views(self):
        self.container = ctk.CTkFrame(self, corner_radius=0, fg_color=T.BG)
        self.container.grid(row=0, column=1, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.icon_manager = IconManager()
        self.winget_manager = WingetManager()

        self.dashboard_view = DashboardView(self.container)
        self.optimizer_view = OptimizerView(self.container)
        self.hub_view = HubView(self.container, self.icon_manager, self.winget_manager)

        self._view_map = {
            "dashboard": self.dashboard_view,
            "optimizer": self.optimizer_view,
            "hub": self.hub_view,
        }
        for view in self._view_map.values():
            view.grid(row=0, column=0, sticky="nsew")

    def _nav_button(self, text, command):
        return T.btn_ghost(self.sidebar_frame, text, command=command, font=T.font(14))

    def _on_closing(self):
        job = getattr(self.dashboard_view, "_after_job", None)
        if job:
            try:
                self.dashboard_view.after_cancel(job)
            except Exception:
                pass
        self.destroy()

    def _refresh_sidebar_counts(self):
        try:
            n = self.hub_view.count_outdated_apps()
            self.updates_count_lbl.configure(text=f"{n} actualizaciones")
        except Exception:
            pass
        if self.winfo_exists():
            self.after(30000, self._refresh_sidebar_counts)

    def _set_active_btn(self, active):
        for btn in (self.btn_dashboard, self.btn_optimizer, self.btn_hub):
            btn.configure(fg_color="transparent", text_color=T.TEXT_SEC)
        active.configure(fg_color=T.ELEVATED, text_color=T.ACCENT)

    def _switch_view(self, view_key: str, active_btn):
        if self._current_view == view_key:
            return

        for key, view in self._view_map.items():
            if key != view_key:
                if self._current_view == key and hasattr(view, "on_hide"):
                    view.on_hide()
                view.grid_remove()

        target = self._view_map[view_key]
        target.grid(row=0, column=0, sticky="nsew")
        self.update_idletasks()

        if hasattr(target, "on_show"):
            target.on_show()

        self._set_active_btn(active_btn)
        self._current_view = view_key

    def show_dashboard(self):
        self._switch_view("dashboard", self.btn_dashboard)

    def show_optimizer(self):
        self._switch_view("optimizer", self.btn_optimizer)

    def show_hub(self):
        self._switch_view("hub", self.btn_hub)
