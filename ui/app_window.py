import json
import os
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from ui.views.dashboard_view import DashboardView
from ui.views.optimizer_view import OptimizerView
from ui.views.hub_view import HubView
from backend.icon_manager import IconManager
from backend.winget_manager import WingetManager
from backend.optimization_engine import OptimizationEngine
from backend.update_manager import UpdateManager
from backend.utils import apply_window_icon, get_base_path
from ui import theme as T
from version import __version__

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


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, info: dict, updater: UpdateManager):
        super().__init__(master)
        self.updater = updater
        self.info = info
        self.title("Actualización disponible")
        self.geometry("460x220")
        self.resizable(False, False)
        self.configure(fg_color=T.BG)
        self.transient(master)
        self.grab_set()

        T.heading(self, f"ResetX v{info['version']}", size=20).pack(pady=(20, 6))
        ctk.CTkLabel(
            self, text="Hay una nueva versión lista para instalar.",
            font=T.font(13), text_color=T.TEXT_SEC,
        ).pack(pady=(0, 12))
        self.status = ctk.CTkLabel(self, text="", font=T.font(11), text_color=T.TEXT_MUTED)
        self.status.pack(pady=(0, 8))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=8)
        T.btn_secondary(row, "Más tarde", command=self.destroy).pack(side="left", padx=6)
        T.btn_primary(row, "Actualizar ahora", command=self._install).pack(side="left", padx=6)

    def _install(self):
        self.status.configure(text="Descargando…")
        ok = self.updater.download_and_install(
            self.info["url"],
            on_progress=lambda m: self.after(0, lambda: self.status.configure(text=m)),
        )
        if ok:
            self.master.destroy()
        else:
            self.status.configure(text="No se pudo actualizar. Inténtalo más tarde.", text_color=T.RED)


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ResetX")
        self.minsize(900, 600)
        self.configure(fg_color=T.BG)
        apply_window_icon(self)

        self._update_manager = UpdateManager()
        self._hub_view = None
        self._all_hub_app_ids = self._load_all_app_ids()

        self._build_sidebar()
        self._build_views()
        self._current_view = None
        self.show_dashboard()

        self.after(50, self._maximize)
        self.after(3000, self._check_app_update)
        self.after(8000, self._refresh_sidebar_counts)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _load_all_app_ids(self) -> list[str]:
        try:
            path = os.path.join(get_base_path(), "data", "apps_database.json")
            with open(path, "r", encoding="utf-8") as f:
                db = json.load(f)
            return [a["id"] for cat in db.get("categorias", []) for a in cat.get("apps", [])]
        except Exception:
            return []

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

    def _ensure_hub_view(self):
        if self._hub_view is not None:
            return self._hub_view
        self._hub_view = HubView(self.container, self.icon_manager, self.winget_manager)
        self._hub_view.grid(row=0, column=0, sticky="nsew")
        self._view_map["hub"] = self._hub_view
        self.winget_manager.on_loaded(self._refresh_sidebar_counts)
        return self._hub_view

    def _build_views(self):
        self.container = ctk.CTkFrame(self, corner_radius=0, fg_color=T.BG)
        self.container.grid(row=0, column=1, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.icon_manager = IconManager()
        self.winget_manager = WingetManager()

        self.dashboard_view = DashboardView(self.container)
        self.optimizer_view = OptimizerView(self.container)

        self._view_map = {
            "dashboard": self.dashboard_view,
            "optimizer": self.optimizer_view,
            "hub": None,
        }
        for key in ("dashboard", "optimizer"):
            self._view_map[key].grid(row=0, column=0, sticky="nsew")

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

    def _check_app_update(self):
        self._update_manager.check_for_update(self._on_update_result)

    def _on_update_result(self, info):
        if info and self.winfo_exists():
            UpdateDialog(self, info, self._update_manager)

    def _refresh_sidebar_counts(self):
        try:
            if self._hub_view:
                n = self._hub_view.count_outdated_apps()
            elif self._all_hub_app_ids:
                n = self.winget_manager.count_all_outdated(self._all_hub_app_ids)
            else:
                n = 0
            self.updates_count_lbl.configure(text=f"{n} actualizaciones")
        except Exception:
            pass
        if self.winfo_exists():
            self.after(60000, self._refresh_sidebar_counts)

    def _set_active_btn(self, active):
        for btn in (self.btn_dashboard, self.btn_optimizer, self.btn_hub):
            btn.configure(fg_color="transparent", text_color=T.TEXT_SEC)
        active.configure(fg_color=T.ELEVATED, text_color=T.ACCENT)

    def _switch_view(self, view_key: str, active_btn):
        if self._current_view == view_key:
            return

        for key, view in self._view_map.items():
            if not view or key == view_key:
                continue
            if self._current_view == key and hasattr(view, "on_hide"):
                view.on_hide()
            view.grid_remove()

        if view_key == "hub":
            target = self._ensure_hub_view()
        else:
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
