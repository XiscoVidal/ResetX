"""App window with crash-safe view switching."""
import os
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont
from backend.icon_manager import IconManager
from backend.winget_manager import WingetManager
from backend.optimization_engine import OptimizationEngine
from backend.update_manager import UpdateManager
from backend.utils import apply_window_icon, get_base_path
from ui import theme as T
from version import __version__

_logo_image = None


def _create_logo_image(size=(140, 40)):
    global _logo_image
    if _logo_image is not None:
        return _logo_image
    logo_path = os.path.join(get_base_path(), "assets", "logo.png")
    if os.path.exists(logo_path):
        img = Image.open(logo_path)
        _logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
        return _logo_image
    img = Image.new("RGBA", (280, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("segoeuib.ttf", 44)
    except Exception:
        font = ImageFont.load_default()
    draw.text((6, 14), "Reset", fill=T.TEXT, font=font)
    draw.text((118, 14), "X", fill=T.ACCENT, font=font)
    _logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=size)
    return _logo_image


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, info, updater):
        super().__init__(master)
        self.updater = updater
        self.info = info
        self.title("Actualizaci\u00f3n disponible")
        self.geometry("460x220")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_PRIMARY)
        self.transient(master)
        self.grab_set()
        T.heading(self, f"ResetX v{info['version']}", size=20).pack(pady=(20, 6))
        ctk.CTkLabel(self, text="Nueva versi\u00f3n lista para instalar.", font=T.font(13), text_color=T.TEXT_SEC).pack(pady=(0, 12))
        self.status = ctk.CTkLabel(self, text="", font=T.font(11), text_color=T.TEXT_MUTED)
        self.status.pack(pady=(0, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=8)
        T.btn_secondary(row, "M\u00e1s tarde", command=self.destroy).pack(side="left", padx=6)
        T.btn_primary(row, "Actualizar ahora", command=self._install).pack(side="left", padx=6)

    def _install(self):
        self.status.configure(text="Descargando\u2026")
        ok = self.updater.download_and_install(
            self.info["url"],
            on_progress=lambda m: self.after(0, lambda: self.status.configure(text=m)),
        )
        if ok:
            self.master.destroy()
        else:
            self.status.configure(text="Error en la actualizaci\u00f3n.", text_color=T.RED)


class SidebarNav(ctk.CTkFrame):
    def __init__(self, master, items, width=220):
        super().__init__(master, width=width, corner_radius=0, fg_color=T.BG_SECONDARY)
        self.grid_propagate(False)
        self.grid_rowconfigure(8, weight=1)
        self._logo = ctk.CTkLabel(self, text="", image=_create_logo_image())
        self._logo.grid(row=0, column=0, padx=T.PAD_MD, pady=(T.PAD_LG, T.PAD_SM))
        sep1 = ctk.CTkFrame(self, fg_color=T.BORDER, height=1, corner_radius=0)
        sep1.grid(row=1, column=0, sticky="ew", padx=T.PAD_MD, pady=(4, 12))
        self._btns = {}
        for i, (key, label, cmd) in enumerate(items):
            btn = T.btn_ghost(self, label, command=cmd, font=T.font(14))
            btn.grid(row=2 + i, column=0, padx=12, pady=3, sticky="ew")
            self._btns[key] = btn
        sep2 = ctk.CTkFrame(self, fg_color=T.BORDER, height=1, corner_radius=0)
        sep2.grid(row=5, column=0, sticky="ew", padx=T.PAD_MD, pady=12)
        self._tweak_lbl = ctk.CTkLabel(self, text=f"{OptimizationEngine.count_available_tweaks()} optimizaciones", font=T.font(11), text_color=T.TEXT_MUTED, anchor="w")
        self._tweak_lbl.grid(row=6, column=0, padx=T.PAD_MD, sticky="ew")
        self._update_lbl = ctk.CTkLabel(self, text="0 actualizaciones", font=T.font(11), text_color=T.TEXT_MUTED, anchor="w")
        self._update_lbl.grid(row=7, column=0, padx=T.PAD_MD, pady=(2, 0), sticky="ew")
        self._ver_lbl = ctk.CTkLabel(self, text=f"v{__version__}", font=T.font(10), text_color=T.TEXT_MUTED)
        self._ver_lbl.grid(row=9, column=0, padx=T.PAD_MD, pady=(0, T.PAD_MD), sticky="w")

    def set_active(self, key):
        for k, btn in self._btns.items():
            btn.configure(
                fg_color=T.ELEVATED if k == key else "transparent",
                text_color=T.ACCENT if k == key else T.TEXT_SEC,
            )

    def set_updates(self, n):
        self._update_lbl.configure(text=f"{n} actualizaciones")


class AppWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ResetX")
        self.minsize(900, 600)
        self.configure(fg_color=T.BG_PRIMARY)
        apply_window_icon(self)
        self._update_mgr = UpdateManager()
        self._views = {}
        self._current_key = None
        self._services = None
        self._switching = False
        self._resize_job = None

        self._nav = SidebarNav(self, [
            ("dashboard", "Dashboard", self._show_dashboard),
            ("optimizer", "Rendimiento", self._show_optimizer),
            ("hub", "Software Hub", self._show_hub),
        ])
        self._nav.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._container = ctk.CTkFrame(self, corner_radius=0, fg_color=T.BG_PRIMARY)
        self._container.grid(row=0, column=1, sticky="nsew")
        self._container.grid_rowconfigure(0, weight=1)
        self._container.grid_columnconfigure(0, weight=1)

        self.after(50, self._maximize)
        self.after(3000, self._check_update)
        self.after(8000, self._refresh_counts)
        self.bind("<Configure>", self._on_window_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._switch_view("dashboard")

    def _maximize(self):
        try:
            self.state("zoomed")
        except Exception:
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        for delay in (150, 400, 800):
            self.after(delay, self._notify_view_resize)

    def _on_window_resize(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(120, self._notify_view_resize)
        self.after(350, self._notify_view_resize)

    def _notify_view_resize(self):
        self._resize_job = None
        view = self._views.get(self._current_key)
        if not view:
            return
        if hasattr(view, "relayout"):
            try:
                view.relayout()
            except Exception:
                pass
        elif hasattr(view, "_on_resize"):
            try:
                view._on_resize()
            except Exception:
                pass

    def _init_services(self):
        if self._services is None:
            im = IconManager()
            wm = WingetManager()
            wm.on_loaded(self._refresh_counts)
            self._services = {"icon_manager": im, "winget_manager": wm}

    def _lazy_view(self, key):
        if key in self._views:
            return self._views[key]
        self._init_services()
        im = self._services["icon_manager"]
        wm = self._services["winget_manager"]
        try:
            if key == "dashboard":
                from ui.views.dashboard_view import DashboardView
                self._views[key] = DashboardView(self._container)
            elif key == "optimizer":
                from ui.views.optimizer_view import OptimizerView
                self._views[key] = OptimizerView(self._container)
            elif key == "hub":
                from ui.views.hub_view import HubView
                self._views[key] = HubView(self._container, im, wm)
        except Exception as e:
            print(f"[ResetX] Error loading view '{key}': {e}")
            return None
        return self._views.get(key)

    def _switch_view(self, key):
        if self._switching or self._current_key == key:
            return
        self._switching = True
        try:
            old = self._views.get(self._current_key)
            if old:
                try:
                    if hasattr(old, "on_hide"):
                        old.on_hide()
                except Exception:
                    pass
                old.grid_remove()
            view = self._lazy_view(key)
            if view is None:
                return
            view.grid(row=0, column=0, sticky="nsew")
            self.update_idletasks()
            try:
                if hasattr(view, "on_show"):
                    view.on_show()
            except Exception:
                pass
            self._nav.set_active(key)
            self._current_key = key
        finally:
            self._switching = False

    def _show_dashboard(self):
        self._switch_view("dashboard")
    def _show_optimizer(self):
        self._switch_view("optimizer")
    def _show_hub(self):
        self._switch_view("hub")

    def _on_closing(self):
        for v in self._views.values():
            try:
                if hasattr(v, "on_hide"):
                    v.on_hide()
            except Exception:
                pass
        self.destroy()

    def _check_update(self):
        self._update_mgr.check_for_update(lambda i: (self._on_update(i) if i and self.winfo_exists() else None))

    def _on_update(self, info):
        UpdateDialog(self, info, self._update_mgr)

    def _refresh_counts(self):
        try:
            hub = self._views.get("hub")
            if hub and hasattr(hub, "count_outdated_apps"):
                self._nav.set_updates(hub.count_outdated_apps())
        except Exception:
            pass
        if self.winfo_exists():
            self.after(60000, self._refresh_counts)
