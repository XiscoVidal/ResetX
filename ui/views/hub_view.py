"""Software Hub with glassmorphism cards and lazy paginated rendering."""
import json
import os
import re
import customtkinter as ctk
from backend.icon_manager import IconManager
from backend.winget_manager import WingetManager
from backend.utils import get_base_path
from ui import theme as T
from ui.widgets import AnimatedProgressBar

PAGE_SIZE_MAX = 18
CARD_MIN_WIDTH = 158
CARD_HEIGHT = 244
CARD_GAP = 6
CAT_COLS = 6
PAGINATION_RESERVE = 80


def _clean_winget_line(line: str) -> str | None:
    clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)
    clean = re.sub(r"[\r\x08]", "", clean).strip()
    if not clean or re.fullmatch(r"[\\|/\-\s]+", clean):
        return None
    if clean.count("\u2588") > 3 or clean.count("\u2591") > 3:
        return None
    return clean


class InstallProgressModal(ctk.CTkToplevel):
    def __init__(self, master, app_names, winget_manager):
        super().__init__(master)
        self._wm = winget_manager
        self.title("Instalando software")
        self.geometry("680x480")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_PRIMARY)
        self.grab_set()
        self.lift()
        self.focus_force()

        self._total = len(app_names)
        self._done = False

        T.heading(self, "Instalando aplicaciones", size=20).pack(pady=(24, 4))
        self._app_lbl = ctk.CTkLabel(
            self, text=f"Preparando {self._total} aplicaci\u00f3n(es)\u2026",
            font=T.font(13), text_color=T.TEXT_SEC,
        )
        self._app_lbl.pack(pady=(0, 14))

        bar_frame = ctk.CTkFrame(self, fg_color="transparent")
        bar_frame.pack(fill="x", padx=40)
        bar_frame.grid_columnconfigure(0, weight=1)
        self._animated = AnimatedProgressBar(bar_frame, height=12)
        self._animated.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._animated.set_indeterminate(True, f"Preparando {self._total} aplicaci\u00f3n(es)\u2026")

        log_outer = T.glass_card(self)
        log_outer.pack(fill="both", expand=True, padx=30, pady=(12, 10))
        self._log_box = ctk.CTkTextbox(
            log_outer, fg_color=T.INSET, text_color=T.TEXT,
            font=T.font(12, mono=True), wrap="word", state="disabled", border_width=0,
        )
        self._log_box.pack(fill="both", expand=True, padx=6, pady=6)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))
        self._cancel_btn = T.btn_secondary(
            btn_frame, "Cancelar", command=self._on_cancel,
            fg_color=T.RED, hover_color="#DC2626", text_color=T.TEXT,
        )
        self._cancel_btn.pack(side="left", padx=6)
        self._close_btn = T.btn_primary(btn_frame, "Cerrar", command=self.destroy)
        self._close_btn.pack(side="left", padx=6)
        self._close_btn.configure(state="disabled", fg_color=T.ELEVATED, text_color=T.TEXT_MUTED)
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

    def _on_close_attempt(self):
        if self._done:
            self.destroy()
        else:
            self._on_cancel()

    def _on_cancel(self):
        self._wm.cancel_active()
        self.append_log("\nCancelaci\u00f3n solicitada\u2026\n")

    def update_progress(self, current, total, app_id):
        if total > 0:
            label = app_id or "..."
            self._animated.set_progress(
                current / total,
                text=f"Instalando {current + 1} de {total} \u2014 {label}",
                state="running",
            )
        if app_id:
            self._app_lbl.configure(text=f"\u25b6  {app_id}")

    def append_log(self, text):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def finish(self, results):
        ok_count = sum(1 for r in results if r["ok"])
        fail_count = len(results) - ok_count
        success = fail_count == 0 and ok_count > 0

        def _summary():
            self._app_lbl.configure(
                text=f"\u2713 {ok_count} instalada(s)   \u2717 {fail_count} fallida(s)",
                text_color=T.GREEN if success else T.AMBER,
            )
            self.append_log("\n--- RESUMEN ---")
            for r in results:
                mark = "\u2713" if r['ok'] else "\u2717"
                self.append_log(f"  {mark}  {r['id']}")
            self._cancel_btn.configure(state="disabled")
            self._close_btn.configure(state="normal", fg_color=T.GREEN, text_color=T.BG_PRIMARY)
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            self._done = True

        self._animated.finish(
            ok_count > 0,
            text=f"Completado: {ok_count}/{len(results)}",
            on_complete=_summary,
        )


class AppCard(ctk.CTkFrame):
    def __init__(self, master, app_data, icon_manager, winget_manager, hub_view=None):
        super().__init__(
            master, fg_color=T.SURFACE, border_color=T.BORDER,
            border_width=1, corner_radius=T.RADIUS_MD, height=CARD_HEIGHT,
        )
        self._data = app_data
        self._icon_mgr = icon_manager
        self._wm = winget_manager
        self._hub = hub_view
        self._last_click = -1

        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent", height=24)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        top.grid_propagate(False)
        self._cb = ctk.CTkCheckBox(
            top, text="", width=20, height=20,
            fg_color=T.ACCENT, border_color=T.BORDER, corner_radius=4,
            command=self._toggle_select,
        )
        self._cb.pack(side="right")

        self._icon_lbl = ctk.CTkLabel(self, text="\u2026", width=56, height=56, font=T.font(20), text_color=T.TEXT_MUTED)
        self._icon_lbl.grid(row=1, column=0, pady=(2, 0))

        def on_icon_loaded(_):
            self.after(0, self._refresh_icon)

        icon_img = icon_manager.get_icon(
            app_data["id"], domain=app_data.get("dominio"),
            size=(56, 56), callback=on_icon_loaded,
        )
        if icon_img:
            self._icon_lbl.configure(image=icon_img, text="")

        self._title_lbl = ctk.CTkLabel(
            self, text=app_data["nombre"],
            font=ctk.CTkFont(family=T.FONT_UI, size=12, weight="bold"),
            text_color=T.TEXT, anchor="center", wraplength=140,
        )
        self._title_lbl.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 1))

        self._desc_lbl = ctk.CTkLabel(
            self, text=app_data["desc"],
            font=T.font(10), text_color=T.TEXT_SEC,
            anchor="center", wraplength=140, justify="center",
        )
        self._desc_lbl.grid(row=3, column=0, sticky="ew", padx=8)

        self._meta_lbl = ctk.CTkLabel(
            self, text=f"{app_data['size']}  \u00b7  {app_data['rating']}",
            font=T.font(9), text_color=T.TEXT_MUTED, anchor="center",
        )
        self._meta_lbl.grid(row=4, column=0, pady=(2, 0))

        self._ver_lbl = ctk.CTkLabel(
            self, text="", font=T.font(9, mono=True), text_color=T.GREEN, anchor="center",
        )
        self._ver_lbl.grid(row=5, column=0, pady=(1, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=6, column=0, sticky="ew", padx=8, pady=(4, 8))
        bottom.grid_columnconfigure(0, weight=1)
        self._status_lbl = ctk.CTkLabel(
            bottom, text="Comprobando\u2026", font=T.font(9, "bold"), text_color=T.TEXT_SEC,
        )
        self._status_lbl.grid(row=0, column=0, sticky="w")
        self._uninstall_btn = T.btn_ghost(
            bottom, "\u2715", command=self._uninstall,
            width=26, height=24, anchor="center", text_color=T.RED,
        )
        self._uninstall_btn.grid(row=0, column=1, sticky="e")
        self._uninstall_btn.grid_remove()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-3>", self._show_context_menu)
        self.after(10, self._bind_all_click)
        self.check_installed_status()

    def set_column_width(self, width):
        self.configure(width=max(140, width))
        self._title_lbl.configure(wraplength=max(100, width - 14))
        self._desc_lbl.configure(wraplength=max(100, width - 14))

    def _refresh_icon(self):
        if not self.winfo_exists():
            return
        if self._data["id"] in self._icon_mgr._loaded_images:
            del self._icon_mgr._loaded_images[self._data["id"]]
        icon_img = self._icon_mgr.get_icon(
            self._data["id"], domain=self._data.get("dominio"), size=(56, 56),
        )
        if icon_img:
            self._icon_lbl.configure(image=icon_img, text="")

    def _uninstall(self):
        if not self._hub:
            return
        import tkinter as tk
        from tkinter import messagebox
        name = self._data["nombre"]
        ok = messagebox.askyesno(
            "Desinstalar",
            f"\u00bfEst\u00e1s seguro de desinstalar {name}?",
            parent=self,
        )
        if ok:
            self._hub.uninstall_app(self)

    def _upgrade(self):
        if self._hub:
            self._hub.upgrade_app(self)

    def _show_context_menu(self, event):
        import tkinter as tk
        menu = tk.Menu(self, tearoff=0, bg=T.SURFACE, fg=T.TEXT, activebackground=T.ELEVATED)
        info = self._wm.get_app_info(self._data["id"])
        if info.get("status") == "installed":
            if info.get("available"):
                menu.add_command(label="Actualizar", command=self._upgrade)
            menu.add_command(label="Desinstalar", command=self._uninstall)
        menu.add_command(label="Seleccionar", command=lambda: (self._cb.select(), self._toggle_select()))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _bind_all_click(self):
        if not self.winfo_exists():
            return
        skip = {str(self._cb)}

        def bind_widget(w):
            if not w.winfo_exists():
                return
            if str(w) in skip:
                return
            try:
                w.bind("<Button-1>", self._on_card_click, add="+")
            except Exception:
                pass
            for child in w.winfo_children():
                bind_widget(child)

        bind_widget(self)

    def _on_card_click(self, event=None):
        if event is not None and event.serial == self._last_click:
            return
        if event is not None:
            self._last_click = event.serial
        if self._cb.cget("state") == "disabled":
            return
        self._cb.select() if not self._cb.get() else self._cb.deselect()
        self._toggle_select()

    def check_installed_status(self):
        if not self.winfo_exists():
            return
        info = self._wm.get_app_info(self._data["id"])
        if info["status"] == "loading":
            self.after(1500, self.check_installed_status)
            return
        if info["status"] == "unavailable":
            self._status_lbl.configure(text="Winget no disponible", text_color=T.AMBER)
        elif info["status"] == "installed":
            self._ver_lbl.configure(text=f"v{info['version']}")
            self._uninstall_btn.grid()
            if info.get("available"):
                self._status_lbl.configure(text="Actualizable", text_color=T.AMBER)
                self._cb.configure(state="normal")
            else:
                self._status_lbl.configure(text="Actualizado", text_color=T.GREEN)
                self._cb.configure(state="disabled")
        else:
            self._uninstall_btn.grid_remove()
            self._status_lbl.configure(text="No instalado", text_color=T.TEXT_SEC)

    def _toggle_select(self):
        sel = bool(self._cb.get())
        self.configure(
            border_color=T.GREEN if sel else T.BORDER,
            border_width=2 if sel else 1,
        )

    def _on_enter(self, _):
        if not self._cb.get():
            self.configure(fg_color=T.SURFACE_HOVER, border_color=T.BORDER_FOCUS)

    def _on_leave(self, _):
        if not self._cb.get():
            self.configure(fg_color=T.SURFACE, border_color=T.BORDER)

    def mark_installing(self):
        self._status_lbl.configure(text="Instalando\u2026", text_color=T.ACCENT)
        self._cb.configure(state="disabled")

    def mark_done(self, ok):
        if ok:
            self._status_lbl.configure(text="Instalado", text_color=T.GREEN)
            self._cb.deselect()
            self._toggle_select()
            self.check_installed_status()
        else:
            self._status_lbl.configure(text="Error", text_color=T.RED)


class HubView(ctk.CTkFrame):
    def __init__(self, master, icon_manager, winget_manager):
        super().__init__(master, fg_color=T.BG_PRIMARY)
        self._icon_mgr = icon_manager
        self._wm = winget_manager

        with open(os.path.join(get_base_path(), "data", "apps_database.json"), "r", encoding="utf-8") as f:
            self._db = json.load(f)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._current_cat = None
        self._cards = []
        self._cat_btns = []
        self._active_cat_btn = None
        self._cols = 4
        self._rows = 2
        self._page_size = 8
        self._page_by_cat = {}
        self._rendering = False
        self._resize_after = None
        self._refresh_job = None
        self._hidden = False
        self._all_app_ids = [a["id"] for cat in self._db.get("categorias", []) for a in cat.get("apps", [])]

        # Top bar
        top_bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0, height=72)
        top_bar.grid(row=0, column=0, sticky="ew")
        top_bar.grid_propagate(False)
        top_bar.grid_columnconfigure(0, weight=1)

        if not self._wm.is_available:
            self._show_winget_unavailable()
            return

        self._search = T.entry(top_bar, placeholder="Buscar software\u2026", width=320)
        self._search.grid(row=0, column=0, padx=T.PAD_LG, pady=T.PAD_MD, sticky="w")
        self._search.bind("<KeyRelease>", self._on_search)

        self._btn_install_cat = T.btn_secondary(
            top_bar, "Instalar categor\u00eda", command=self._install_all_category,
        )
        self._btn_install_cat.grid(row=0, column=1, padx=(0, 8), pady=T.PAD_MD, sticky="e")

        self._btn_install = T.btn_primary(
            top_bar, "Instalar seleccionados", command=self._start_install,
        )
        self._btn_install.grid(row=0, column=2, padx=(0, T.PAD_LG), pady=T.PAD_MD, sticky="e")

        # Category bar
        cat_bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0)
        cat_bar.grid(row=1, column=0, sticky="ew")
        self._cat_inner = ctk.CTkFrame(cat_bar, fg_color="transparent")
        self._cat_inner.pack(fill="x", padx=10, pady=6)
        for c in range(CAT_COLS):
            self._cat_inner.grid_columnconfigure(c, weight=1)

        self._refresh_category_buttons()

        # Content
        self._shell = ctk.CTkFrame(self, fg_color=T.BG_PRIMARY)
        self._shell.grid(row=2, column=0, sticky="nsew", padx=T.PAD_SM, pady=(0, T.PAD_SM))
        self._shell.grid_rowconfigure(0, weight=0)
        self._shell.grid_columnconfigure(0, weight=1)
        self._shell.bind("<Configure>", self._on_resize)

        self._cards_container = ctk.CTkFrame(self._shell, fg_color=T.BG_PRIMARY)
        self._cards_container.grid(row=0, column=0, sticky="ew")

        self._empty_lbl = ctk.CTkLabel(
            self._shell, text="", font=T.font(13), text_color=T.TEXT_SEC,
        )

        self._pagination = T.glass_card(self._shell)
        self._pagination.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._pagination.grid_columnconfigure(1, weight=1)

        self._btn_prev = T.btn_secondary(
            self._pagination, "\u2039", width=36, command=lambda: self._change_page(-1),
        )
        self._btn_prev.grid(row=0, column=0, padx=(12, 4), pady=10)

        self._page_btns_frame = ctk.CTkFrame(self._pagination, fg_color="transparent")
        self._page_btns_frame.grid(row=0, column=1, pady=10)

        self._btn_next = T.btn_secondary(
            self._pagination, "\u203a", width=36, command=lambda: self._change_page(1),
        )
        self._btn_next.grid(row=0, column=2, padx=(4, 12), pady=10)

        self._status_lbl = ctk.CTkLabel(
            self._pagination, text="", font=T.font(12), text_color=T.TEXT_SEC,
        )
        self._status_lbl.grid(row=1, column=0, columnspan=3, pady=(0, 10))

        if self._db["categorias"]:
            self.load_category(self._db["categorias"][0], self._cat_btns[0])
        self._wm.on_loaded(self._on_winget_loaded)

    def _show_winget_unavailable(self):
        msg = T.glass_card(self)
        msg.place(relx=0.5, rely=0.5, anchor="center")
        T.heading(msg, "Winget no est\u00e1 instalado", size=20).pack(padx=40, pady=(28, 8))
        ctk.CTkLabel(
            msg,
            text="Instala App Installer desde Microsoft Store\npara usar el Software Hub.",
            font=T.font(13), text_color=T.TEXT_SEC, justify="center",
        ).pack(padx=40, pady=(0, 28))

    def _refresh_category_buttons(self):
        if self._hidden or not hasattr(self, "_cat_inner"):
            return
        prev_cat = self._current_cat
        for btn in self._cat_btns:
            try:
                btn.destroy()
            except Exception:
                pass
        self._cat_btns.clear()
        self._active_cat_btn = None
        for i, cat in enumerate(self._db["categorias"]):
            row, col = divmod(i, CAT_COLS)
            updates = self._wm.count_updates_in_apps([a["id"] for a in cat["apps"]])
            badge = f" \u00b7{updates}\u2191" if updates else ""
            btn = ctk.CTkButton(
                self._cat_inner,
                text=f"{cat['nombre']} ({len(cat['apps'])}){badge}",
                font=T.font(12), height=32,
                fg_color="transparent", hover_color=T.ELEVATED,
                text_color=T.TEXT_SEC, corner_radius=T.RADIUS_SM,
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
            btn.configure(command=lambda c=cat, b=btn: self.load_category(c, b))
            self._cat_btns.append(btn)
            if prev_cat and cat["id"] == prev_cat["id"]:
                self._active_cat_btn = btn
                btn.configure(fg_color=T.ELEVATED, text_color=T.ACCENT)

    def count_outdated_apps(self):
        return self._wm.count_all_outdated(self._all_app_ids)

    def _on_winget_loaded(self):
        if self._hidden or not self._cat_btns:
            return
        self._refresh_category_buttons()
        for card in self._cards:
            card.check_installed_status()

    def _on_resize(self, _=None):
        if self._hidden or not self._current_cat or self._rendering:
            return
        if self._resize_after:
            try:
                self.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.after(120, self._apply_resize)

    def _apply_resize(self):
        self._resize_after = None
        if self._hidden or not self._current_cat or self._rendering:
            return
        cols, rows, page_size = self._calc_page_size()
        if cols != self._cols or rows != self._rows or page_size != self._page_size:
            self._cols, self._rows, self._page_size = cols, rows, page_size
            self._render_page()

    def _get_columns(self):
        w = self._cards_container.winfo_width()
        if w < 80:
            w = self._shell.winfo_width()
        if w < 80:
            return self._cols
        return max(2, min(6, (w + CARD_GAP) // (CARD_MIN_WIDTH + CARD_GAP)))

    def _get_rows(self, cols):
        row_unit = CARD_HEIGHT + CARD_GAP
        avail = self._available_height()
        return max(1, min(4, max(1, avail // row_unit)))

    def _available_height(self):
        self.update_idletasks()
        shell_h = self._shell.winfo_height()
        if shell_h > 120:
            pag_h = max(getattr(self._pagination, "winfo_height", lambda: PAGINATION_RESERVE)(), PAGINATION_RESERVE)
            return max(CARD_HEIGHT, shell_h - pag_h - 12)
        win_h = self.winfo_height()
        return max(CARD_HEIGHT, (win_h - 300) if win_h > 200 else CARD_HEIGHT * 2)

    def _calc_page_size(self):
        cols = self._get_columns()
        rows = self._get_rows(cols)
        return cols, rows, min(PAGE_SIZE_MAX, cols * rows)

    def _filtered_apps(self):
        if not self._current_cat:
            return []
        q = self._search.get().strip().lower()
        apps = self._current_cat["apps"]
        if not q:
            return apps
        return [a for a in apps if q in a["nombre"].lower() or q in a["desc"].lower()]

    def _page_info(self):
        apps = self._filtered_apps()
        total = len(apps)
        self._cols, self._rows, self._page_size = self._calc_page_size()
        ps = self._page_size
        total_pages = max(1, (total + ps - 1) // ps) if total else 1
        cat_id = self._current_cat["id"]
        page = self._page_by_cat.get(cat_id, 0)
        page = max(0, min(page, total_pages - 1))
        self._page_by_cat[cat_id] = page
        return page, total_pages, total

    def _clear_cards(self):
        for card in self._cards:
            card.destroy()
        self._cards.clear()

    def _render_page(self):
        if self._hidden or not self._current_cat or self._rendering:
            return
        self._rendering = True
        self._clear_cards()
        try:
            apps = self._filtered_apps()
            page, total_pages, total = self._page_info()
            ps = self._page_size
            start = page * ps
            end = min(start + ps, total)
            page_apps = apps[start:end]
            cols = self._cols
            col_w = max(CARD_MIN_WIDTH, (
                self._cards_container.winfo_width() - CARD_GAP * (cols + 1)
            ) // cols) if self._cards_container.winfo_width() > 80 else CARD_MIN_WIDTH

            for i in range(cols):
                self._cards_container.grid_columnconfigure(i, weight=1, uniform="hub_cols")
            for r in range(self._rows):
                self._cards_container.grid_rowconfigure(r, weight=0, minsize=CARD_HEIGHT + CARD_GAP)

            for i, app in enumerate(page_apps):
                row, col = divmod(i, cols)
                card = AppCard(self._cards_container, app, self._icon_mgr, self._wm, hub_view=self)
                card.set_column_width(col_w)
                card.grid(row=row, column=col, padx=CARD_GAP // 2, pady=CARD_GAP // 2, sticky="nsew")
                self._cards.append(card)

            show_start = start + 1 if total else 0
            self._set_pagination(page, total_pages, show_start, end, total)
        finally:
            self._rendering = False

    def _set_pagination(self, page, total_pages, start, end, total):
        self._empty_lbl.grid_remove()
        self._cards_container.grid(row=0, column=0, sticky="ew")
        if total == 0:
            self._cards_container.grid_remove()
            self._empty_lbl.configure(text="Sin resultados")
            self._empty_lbl.grid(row=0, column=0, pady=40)
            self._status_lbl.configure(text="0 aplicaciones")
        else:
            self._status_lbl.configure(text=f"Mostrando {start}\u2013{end} de {total}")
        self._btn_prev.configure(state="normal" if page > 0 else "disabled")
        self._btn_next.configure(state="normal" if page < total_pages - 1 else "disabled")
        self._rebuild_page_btns(page, total_pages)

    def _rebuild_page_btns(self, page, total_pages):
        for w in self._page_btns_frame.winfo_children():
            w.destroy()
        if total_pages <= 1:
            return
        window = 5
        start_p = max(0, min(page - window // 2, total_pages - window))
        end_p = min(total_pages, start_p + window)
        for p in range(start_p, end_p):
            active = p == page
            btn = T.btn_secondary(
                self._page_btns_frame, text=str(p + 1), width=36,
                command=lambda pg=p: self._go_to_page(pg),
                fg_color=T.ACCENT if active else T.ELEVATED,
                text_color=T.BG_PRIMARY if active else T.TEXT,
            )
            btn.pack(side="left", padx=2)

    def _go_to_page(self, page):
        if not self._current_cat:
            return
        self._page_by_cat[self._current_cat["id"]] = page
        self._render_page()

    def _change_page(self, delta):
        if not self._current_cat:
            return
        page, total_pages, _ = self._page_info()
        new_page = max(0, min(page + delta, total_pages - 1))
        self._page_by_cat[self._current_cat["id"]] = new_page
        self._render_page()

    def _on_search(self, _=None):
        if not self._current_cat:
            return
        self._page_by_cat[self._current_cat["id"]] = 0
        self._render_page()

    def load_category(self, cat_data, active_btn):
        self._search.delete(0, "end")
        for btn in self._cat_btns:
            btn.configure(fg_color="transparent", text_color=T.TEXT_SEC)
        active_btn.configure(fg_color=T.ELEVATED, text_color=T.ACCENT)
        self._active_cat_btn = active_btn
        self._current_cat = cat_data
        self._page_by_cat[cat_data["id"]] = 0
        self._render_page()

    def on_show(self):
        self._hidden = False
        self.update_idletasks()
        cols, rows, ps = self._calc_page_size()
        if self._current_cat and (cols != self._cols or rows != self._rows or ps != self._page_size):
            self._cols, self._rows, self._page_size = cols, rows, ps
            self._render_page()
        if self._refresh_job is None:
            self._refresh_job = self.after(4000, self._refresh_category_buttons)
        self._on_resize()

    def on_hide(self):
        self._hidden = True
        if self._resize_after:
            try:
                self.after_cancel(self._resize_after)
            except Exception:
                pass
            self._resize_after = None
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None

    def _install_all_category(self):
        if not self._current_cat:
            return
        to_install = [
            a["id"] for a in self._current_cat["apps"]
            if self._wm.get_app_info(a["id"]).get("status") != "installed"
        ]
        if not to_install:
            orig = self._btn_install_cat.cget("text")
            self._btn_install_cat.configure(text="Todo instalado")
            self.after(2000, lambda: self._btn_install_cat.configure(text=orig))
            return
        self._run_install(to_install)

    def _start_install(self):
        selected = [c for c in self._cards if c._cb.get()]
        if not selected:
            orig = self._btn_install.cget("text")
            self._btn_install.configure(text="Selecciona apps primero", fg_color=T.AMBER)
            self.after(2000, lambda: self._btn_install.configure(text=orig, fg_color=T.GREEN))
            return
        self._run_install([c._data["id"] for c in selected], selected)

    def _run_install(self, app_ids, selected_cards=None):
        self._btn_install.configure(state="disabled", text="Instalando\u2026")
        modal = InstallProgressModal(self.winfo_toplevel(), app_ids, self._wm)
        card_map = {
            c._data["id"]: c for c in (selected_cards or self._cards)
            if c._data["id"] in app_ids
        }
        for c in card_map.values():
            c.mark_installing()

        def on_progress(current, total, app_id):
            if not self._hidden:
                self.after(0, lambda: modal.update_progress(current, total, app_id))

        def on_log(line):
            if self._hidden:
                return
            cleaned = _clean_winget_line(line)
            if cleaned:
                self.after(0, lambda l=cleaned: modal.append_log(l))

        def on_done(results):
            if not self._hidden:
                for r in results:
                    card = card_map.get(r["id"])
                    if card:
                        self.after(0, lambda c=card, ok=r["ok"]: c.mark_done(ok))
                self.after(0, lambda: modal.finish(results))
                self.after(0, lambda: self._btn_install.configure(state="normal", text="Instalar seleccionados"))
                self.after(0, self._render_page)
                self.after(500, self._refresh_category_buttons)

        self._wm.install_apps(app_ids, on_progress=on_progress, on_log=on_log, on_done=on_done)

    def uninstall_app(self, card):
        card._status_lbl.configure(text="Desinstalando\u2026", text_color=T.ACCENT)

        def on_done(_):
            if not self._hidden:
                self.after(0, self._render_page)
                self.after(500, self._refresh_category_buttons)

        self._wm.uninstall_app(card._data["id"], on_done=on_done)

    def upgrade_app(self, card):
        card.mark_installing()

        def on_done(results):
            if not self._hidden:
                ok = bool(results and results[0].get("ok"))
                self.after(0, lambda: card.mark_done(ok))
                self.after(0, self._render_page)
                self.after(500, self._refresh_category_buttons)

        self._wm.upgrade_apps([card._data["id"]], on_done=on_done)
