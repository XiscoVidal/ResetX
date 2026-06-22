import json
import os
import re
import tkinter as tk
import customtkinter as ctk
from backend.icon_manager import IconManager
from backend.winget_manager import WingetManager
from backend.utils import get_base_path
from ui import theme as T
from ui.widgets.animated_progress import AnimatedProgressBar

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
    if clean.count("█") > 3 or clean.count("░") > 3:
        return None
    return clean


class InstallProgressModal(ctk.CTkToplevel):
    def __init__(self, master, app_names: list[str], winget_manager: WingetManager):
        super().__init__(master)
        self.winget_manager = winget_manager
        self.title("Instalando software")
        self.geometry("680x480")
        self.resizable(False, False)
        self.configure(fg_color=T.BG)
        self.grab_set()
        self.lift()
        self.focus_force()

        self._total = len(app_names)
        self._done = False

        T.heading(self, "Instalando aplicaciones", size=20).pack(pady=(24, 4))
        self._app_lbl = ctk.CTkLabel(
            self, text=f"Preparando {self._total} aplicación(es)…",
            font=T.font(13), text_color=T.TEXT_SEC,
        )
        self._app_lbl.pack(pady=(0, 14))

        bar_frame = ctk.CTkFrame(self, fg_color="transparent")
        bar_frame.pack(fill="x", padx=40)
        bar_frame.grid_columnconfigure(0, weight=1)

        self._animated = AnimatedProgressBar(bar_frame, height=12)
        self._animated.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self._animated.set_indeterminate(True, f"Preparando {self._total} aplicación(es)…")

        log_outer = T.card(self, corner_radius=T.RADIUS_MD)
        log_outer.pack(fill="both", expand=True, padx=30, pady=(12, 10))
        self._log_box = ctk.CTkTextbox(
            log_outer, fg_color=T.INSET, text_color=T.TEXT,
            font=T.font(12, mono=True), wrap="word", state="disabled", border_width=0,
        )
        self._log_box.pack(fill="both", expand=True, padx=6, pady=6)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))
        self._cancel_btn = T.btn_secondary(btn_frame, "Cancelar", command=self._on_cancel, fg_color=T.RED, hover_color="#DC2626", text_color=T.TEXT)
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
        self.winget_manager.cancel_active()
        self.append_log("\nCancelación solicitada…\n")

    def update_progress(self, current: int, total: int, app_id: str):
        if total > 0:
            pct = current / total
            name = app_id or "…"
            self._animated.set_progress(
                pct,
                text=f"Instalando {current + 1} de {total} — {name}",
                state="running",
            )
        if app_id:
            self._app_lbl.configure(text=f"▶  {app_id}")

    def append_log(self, text: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def finish(self, results: list[dict]):
        ok_count = sum(1 for r in results if r["ok"])
        fail_count = len(results) - ok_count
        success = fail_count == 0 and ok_count > 0

        def _show_summary():
            self._app_lbl.configure(
                text=f"✓ {ok_count} instalada(s)   ✗ {fail_count} fallida(s)",
                text_color=T.GREEN if success else T.AMBER,
            )
            self.append_log("\n── RESUMEN ──")
            for r in results:
                self.append_log(f"  {'✓' if r['ok'] else '✗'}  {r['id']}")
            self._cancel_btn.configure(state="disabled")
            self._close_btn.configure(state="normal", fg_color=T.GREEN, text_color=T.BG)
            self.protocol("WM_DELETE_WINDOW", self.destroy)
            self._done = True

        self._animated.finish(
            ok_count > 0,
            text=f"Completado: {ok_count}/{len(results)}",
            on_complete=_show_summary,
        )


class AppCard(ctk.CTkFrame):
    """Tarjeta de aplicación del Hub."""

    def __init__(self, master, app_data, icon_manager: IconManager, winget_manager: WingetManager, hub_view=None):
        super().__init__(
            master, fg_color=T.SURFACE, border_color=T.BORDER, border_width=1,
            corner_radius=T.RADIUS_MD, height=CARD_HEIGHT,
        )
        self.app_data = app_data
        self.icon_manager = icon_manager
        self.winget_manager = winget_manager
        self.hub_view = hub_view
        self._last_click_serial = -1

        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent", height=24)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        top.grid_propagate(False)
        self.checkbox = ctk.CTkCheckBox(
            top, text="", width=20, height=20,
            fg_color=T.ACCENT, border_color=T.BORDER, corner_radius=4, command=self.toggle_select,
        )
        self.checkbox.pack(side="right")

        self.icon_label = ctk.CTkLabel(
            self, text="…", width=56, height=56,
            font=T.font(20), text_color=T.TEXT_MUTED,
        )
        self.icon_label.grid(row=1, column=0, pady=(2, 0))

        def on_icon_loaded(_app_id):
            self.after(0, self._refresh_icon)

        icon_img = icon_manager.get_icon(
            app_data["id"], domain=app_data.get("dominio"), size=(56, 56), callback=on_icon_loaded,
        )
        if icon_img:
            self.icon_label.configure(image=icon_img, text="")

        self.title_lbl = ctk.CTkLabel(
            self,
            text=app_data["nombre"],
            font=ctk.CTkFont(family=T.FONT_UI, size=12, weight="bold"),
            text_color=T.TEXT,
            anchor="center",
            wraplength=140,
        )
        self.title_lbl.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 1))

        self.desc = ctk.CTkLabel(
            self, text=app_data["desc"],
            font=T.font(10), text_color=T.TEXT_SEC,
            anchor="center", wraplength=140, justify="center",
        )
        self.desc.grid(row=3, column=0, sticky="ew", padx=8)

        self.meta_lbl = ctk.CTkLabel(
            self, text=f"{app_data['size']}  ·  {app_data['rating']}",
            font=T.font(9), text_color=T.TEXT_MUTED, anchor="center",
        )
        self.meta_lbl.grid(row=4, column=0, pady=(2, 0))

        self.version_lbl = ctk.CTkLabel(
            self, text="", font=T.font(9, mono=True), text_color=T.GREEN, anchor="center",
        )
        self.version_lbl.grid(row=5, column=0, pady=(1, 0))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=6, column=0, sticky="ew", padx=8, pady=(4, 8))
        bottom.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(bottom, text="Comprobando…", font=T.font(9, "bold"), text_color=T.TEXT_SEC)
        self.status.grid(row=0, column=0, sticky="w")
        self.uninstall_btn = T.btn_ghost(
            bottom, "✕", command=self._uninstall, width=26, height=24,
            anchor="center", text_color=T.RED,
        )
        self.uninstall_btn.grid(row=0, column=1, sticky="e")
        self.uninstall_btn.grid_remove()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-3>", self._show_context_menu)
        self.after(10, self._bind_all_click)
        self.check_installed_status()

    def set_column_width(self, width: int):
        self.configure(width=max(140, width))
        wrap = max(100, width - 14)
        self.title_lbl.configure(wraplength=wrap)
        self.desc.configure(wraplength=wrap)

    def _refresh_icon(self):
        if self.app_data["id"] in self.icon_manager._loaded_images:
            del self.icon_manager._loaded_images[self.app_data["id"]]
        icon_img = self.icon_manager.get_icon(
            self.app_data["id"], domain=self.app_data.get("dominio"), size=(56, 56),
        )
        if icon_img:
            self.icon_label.configure(image=icon_img, text="")

    def _show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg=T.SURFACE, fg=T.TEXT, activebackground=T.ELEVATED)
        if self.winget_manager.get_app_info(self.app_data["id"]).get("status") == "installed":
            menu.add_command(label="Desinstalar", command=self._uninstall)
        menu.add_command(label="Seleccionar", command=lambda: (self.checkbox.select(), self.toggle_select()))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _uninstall(self):
        if self.hub_view:
            self.hub_view.uninstall_app(self)

    def _bind_all_click(self):
        skip = set()

        def collect(w):
            skip.add(str(w))
            for c in w.winfo_children():
                collect(c)

        collect(self.checkbox)

        def bind_widget(w):
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
        if event is not None and event.serial == self._last_click_serial:
            return
        if event is not None:
            self._last_click_serial = event.serial
        if self.checkbox.cget("state") == "disabled":
            return
        self.checkbox.select() if not self.checkbox.get() else self.checkbox.deselect()
        self.toggle_select()

    def check_installed_status(self):
        info = self.winget_manager.get_app_info(self.app_data["id"])
        if info["status"] == "loading":
            self.after(1000, self.check_installed_status)
        elif info["status"] == "unavailable":
            self.status.configure(text="Winget no disponible", text_color=T.AMBER)
        elif info["status"] == "installed":
            self.version_lbl.configure(text=f"v{info['version']}")
            self.uninstall_btn.grid()
            if info.get("available"):
                self.status.configure(text="Actualizable", text_color=T.AMBER)
                self.checkbox.configure(state="normal")
            else:
                self.status.configure(text="Actualizado", text_color=T.GREEN)
                self.checkbox.configure(state="disabled")
        else:
            self.uninstall_btn.grid_remove()
            self.status.configure(text="No instalado", text_color=T.TEXT_SEC)

    def toggle_select(self):
        selected = bool(self.checkbox.get())
        self.configure(border_color=T.GREEN if selected else T.BORDER, border_width=2 if selected else 1)

    def _on_enter(self, _):
        if not self.checkbox.get():
            self.configure(fg_color=T.SURFACE_HOVER, border_color=T.BORDER_FOCUS)

    def _on_leave(self, _):
        if not self.checkbox.get():
            self.configure(fg_color=T.SURFACE, border_color=T.BORDER)

    def mark_installing(self):
        self.status.configure(text="Instalando…", text_color=T.ACCENT)
        self.checkbox.configure(state="disabled")

    def mark_done(self, ok: bool):
        if ok:
            self.status.configure(text="Instalado", text_color=T.GREEN)
            self.checkbox.deselect()
            self.toggle_select()
            self.check_installed_status()
        else:
            self.status.configure(text="Error", text_color=T.RED)


class HubView(ctk.CTkFrame):
    """
    Hub con paginación clásica por categoría.
    Solo se crean tarjetas de la página actual (PAGE_SIZE apps).
    """

    def __init__(self, master, icon_manager, winget_manager):
        super().__init__(master, fg_color=T.BG)
        self.icon_manager = icon_manager
        self.winget_manager = winget_manager

        with open(os.path.join(get_base_path(), "data", "apps_database.json"), "r", encoding="utf-8") as f:
            self.db = json.load(f)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.current_category = None
        self.current_cards: list[AppCard] = []
        self._active_category_btn = None
        self._columns = 4
        self._rows = 2
        self._page_size = 8
        self._page_by_cat: dict[str, int] = {}
        self._rendering = False

        # ── Top bar ──
        self.top_bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0, height=72)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.top_bar.grid_propagate(False)
        self.top_bar.grid_columnconfigure(0, weight=1)

        if not self.winget_manager.is_available:
            self._show_winget_unavailable()
            return

        self.search_entry = T.entry(self.top_bar, placeholder="Buscar software…", width=320)
        self.search_entry.grid(row=0, column=0, padx=T.PAD_LG, pady=T.PAD_MD, sticky="w")
        self.search_entry.bind("<KeyRelease>", self._on_search)

        self.btn_install_category = T.btn_secondary(self.top_bar, "Instalar categoría", command=self._install_all_category)
        self.btn_install_category.grid(row=0, column=1, padx=(0, 8), pady=T.PAD_MD, sticky="e")

        self.btn_install_all = T.btn_primary(self.top_bar, "Instalar seleccionados", command=self._start_install)
        self.btn_install_all.grid(row=0, column=2, padx=(0, T.PAD_LG), pady=T.PAD_MD, sticky="e")

        # ── Categorías (barra horizontal, sin scroll) ──
        self.category_bar = ctk.CTkFrame(self, fg_color=T.SURFACE, corner_radius=0)
        self.category_bar.grid(row=1, column=0, sticky="ew")
        self.category_inner = ctk.CTkFrame(self.category_bar, fg_color="transparent")
        self.category_inner.pack(fill="x", padx=10, pady=6)
        for c in range(CAT_COLS):
            self.category_inner.grid_columnconfigure(c, weight=1)

        self.category_buttons: list[ctk.CTkButton] = []
        self._refresh_category_buttons()

        # ── Contenido (grid de apps + paginación, sin scroll) ──
        self.content_shell = ctk.CTkFrame(self, fg_color=T.BG)
        self.content_shell.grid(row=2, column=0, sticky="nsew", padx=T.PAD_SM, pady=(0, T.PAD_SM))
        self.content_shell.grid_rowconfigure(0, weight=0)
        self.content_shell.grid_columnconfigure(0, weight=1)
        self.content_shell.bind("<Configure>", self._on_container_resize)

        self.cards_container = ctk.CTkFrame(self.content_shell, fg_color=T.BG)
        self.cards_container.grid(row=0, column=0, sticky="ew")

        self.empty_lbl = ctk.CTkLabel(
            self.content_shell, text="", font=T.font(13), text_color=T.TEXT_SEC,
        )

        self.pagination_bar = T.card(self.content_shell, corner_radius=T.RADIUS_SM)
        self.pagination_bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.pagination_bar.grid_columnconfigure(1, weight=1)

        self.btn_prev = T.btn_secondary(self.pagination_bar, "‹", width=36, command=lambda: self._change_page(-1))
        self.btn_prev.grid(row=0, column=0, padx=(12, 4), pady=10)

        self.page_buttons_frame = ctk.CTkFrame(self.pagination_bar, fg_color="transparent")
        self.page_buttons_frame.grid(row=0, column=1, pady=10)

        self.btn_next = T.btn_secondary(self.pagination_bar, "›", width=36, command=lambda: self._change_page(1))
        self.btn_next.grid(row=0, column=2, padx=(4, 12), pady=10)

        self.status_lbl = ctk.CTkLabel(
            self.pagination_bar, text="",
            font=T.font(12), text_color=T.TEXT_SEC,
        )
        self.status_lbl.grid(row=1, column=0, columnspan=3, pady=(0, 10))

        if self.db["categorias"]:
            self.load_category(self.db["categorias"][0], self.category_buttons[0])
        self.after(4000, self._refresh_category_buttons)
        self.after(250, self._on_container_resize)

    def apply_theme(self):
        for card in self.current_cards:
            card.configure(fg_color=T.SURFACE, border_color=T.BORDER if not card.checkbox.get() else T.GREEN)
            card.title_lbl.configure(text_color=T.TEXT)
            card.desc.configure(text_color=T.TEXT_SEC)
            card.meta_lbl.configure(text_color=T.TEXT_MUTED)

    def on_show(self):
        self.update_idletasks()
        cols, rows, page_size = self._calc_page_size()
        if self.current_category and (
            cols != self._columns or rows != self._rows or page_size != self._page_size
        ):
            self._columns, self._rows, self._page_size = cols, rows, page_size
            self._render_current_page()

    def _show_winget_unavailable(self):
        msg = T.card(self)
        msg.place(relx=0.5, rely=0.5, anchor="center")
        T.heading(msg, "Winget no está instalado", size=20).pack(padx=40, pady=(28, 8))
        ctk.CTkLabel(
            msg,
            text="Instala App Installer desde Microsoft Store\npara usar el Software Hub.",
            font=T.font(13), text_color=T.TEXT_SEC, justify="center",
        ).pack(padx=40, pady=(0, 28))

    def _refresh_category_buttons(self):
        prev_cat = self.current_category
        for btn in self.category_buttons:
            btn.destroy()
        self.category_buttons.clear()
        self._active_category_btn = None
        for i, cat in enumerate(self.db["categorias"]):
            row, col = divmod(i, CAT_COLS)
            updates = self.winget_manager.count_updates_in_apps([a["id"] for a in cat["apps"]])
            badge = f" ·{updates}↑" if updates else ""
            short = cat["nombre"]
            btn = ctk.CTkButton(
                self.category_inner,
                text=f"{short} ({len(cat['apps'])}){badge}",
                font=T.font(12),
                height=32,
                fg_color="transparent",
                hover_color=T.ELEVATED,
                text_color=T.TEXT_SEC,
                corner_radius=T.RADIUS_SM,
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="ew")
            btn.configure(command=lambda c=cat, b=btn: self.load_category(c, b))
            self.category_buttons.append(btn)
            if prev_cat and cat["id"] == prev_cat["id"]:
                self._active_category_btn = btn
                btn.configure(fg_color=T.ELEVATED, text_color=T.ACCENT)

    def count_outdated_apps(self) -> int:
        return sum(
            self.winget_manager.count_updates_in_apps([a["id"] for a in cat["apps"]])
            for cat in self.db["categorias"]
        )

    def _available_cards_height(self) -> int:
        self.update_idletasks()
        shell_h = self.content_shell.winfo_height()
        if shell_h > 120:
            pag_h = max(self.pagination_bar.winfo_height(), PAGINATION_RESERVE)
            return max(CARD_HEIGHT, shell_h - pag_h - 12)
        win_h = self.winfo_height()
        if win_h > 200:
            return max(CARD_HEIGHT, win_h - 300)
        return CARD_HEIGHT * 2

    def _get_columns(self) -> int:
        w = self.cards_container.winfo_width()
        if w < 80:
            w = self.content_shell.winfo_width()
        if w < 80:
            return self._columns
        cell = CARD_MIN_WIDTH + CARD_GAP
        return max(2, min(6, (w + CARD_GAP) // cell))

    def _column_width(self, cols: int) -> int:
        w = self.cards_container.winfo_width()
        if w < 80:
            w = self.content_shell.winfo_width()
        if w < 80:
            return CARD_MIN_WIDTH
        return max(CARD_MIN_WIDTH, (w - CARD_GAP * (cols + 1)) // cols)

    def _get_rows(self, cols: int) -> int:
        avail = self._available_cards_height()
        row_unit = CARD_HEIGHT + CARD_GAP
        rows = max(1, avail // row_unit)
        return max(1, min(4, rows))

    def _calc_page_size(self) -> tuple[int, int, int]:
        cols = self._get_columns()
        rows = self._get_rows(cols)
        size = min(PAGE_SIZE_MAX, cols * rows)
        return cols, rows, size

    def _on_container_resize(self, event=None):
        if not self.current_category or self._rendering:
            return
        cols, rows, page_size = self._calc_page_size()
        if cols != self._columns or rows != self._rows or page_size != self._page_size:
            self._columns = cols
            self._rows = rows
            self._page_size = page_size
            self._render_current_page()

    def _filtered_apps(self) -> list[dict]:
        if not self.current_category:
            return []
        query = self.search_entry.get().strip().lower()
        apps = self.current_category["apps"]
        if not query:
            return apps
        return [
            a for a in apps
            if query in a["nombre"].lower() or query in a["desc"].lower()
        ]

    def _page_info(self) -> tuple[int, int, int]:
        """Devuelve (page_index, total_pages, total_apps)."""
        apps = self._filtered_apps()
        total = len(apps)
        self._columns, self._rows, self._page_size = self._calc_page_size()
        page_size = self._page_size
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
        cat_id = self.current_category["id"]
        page = self._page_by_cat.get(cat_id, 0)
        page = max(0, min(page, total_pages - 1))
        self._page_by_cat[cat_id] = page
        return page, total_pages, total

    def _clear_cards(self):
        for card in self.current_cards:
            card.destroy()
        self.current_cards.clear()

    def _set_pagination_idle(self, page: int, total_pages: int, start: int, end: int, total: int):
        self.empty_lbl.grid_remove()
        self.cards_container.grid(row=0, column=0, sticky="ew")
        if total == 0:
            self.cards_container.grid_remove()
            self.empty_lbl.configure(text="Sin resultados")
            self.empty_lbl.grid(row=0, column=0, pady=40)
            self.status_lbl.configure(text="0 aplicaciones")
        else:
            self.status_lbl.configure(text=f"Mostrando {start}–{end} de {total}")
        self.btn_prev.configure(state="normal" if page > 0 else "disabled")
        self.btn_next.configure(state="normal" if page < total_pages - 1 else "disabled")
        self._rebuild_page_buttons(page, total_pages)

    def _rebuild_page_buttons(self, page: int, total_pages: int):
        for w in self.page_buttons_frame.winfo_children():
            w.destroy()
        if total_pages <= 1:
            return
        # Ventana de hasta 5 números de página
        window = 5
        start_p = max(0, min(page - window // 2, total_pages - window))
        end_p = min(total_pages, start_p + window)
        for p in range(start_p, end_p):
            is_active = p == page
            btn = T.btn_secondary(
                self.page_buttons_frame,
                text=str(p + 1),
                width=36,
                command=lambda pg=p: self._go_to_page(pg),
                fg_color=T.ACCENT if is_active else T.ELEVATED,
                text_color=T.BG if is_active else T.TEXT,
            )
            btn.pack(side="left", padx=2)

    def _go_to_page(self, page: int):
        if not self.current_category:
            return
        self._page_by_cat[self.current_category["id"]] = page
        self._render_current_page()

    def _change_page(self, delta: int):
        if not self.current_category:
            return
        page, total_pages, _ = self._page_info()
        new_page = max(0, min(page + delta, total_pages - 1))
        self._page_by_cat[self.current_category["id"]] = new_page
        self._render_current_page()

    def _render_current_page(self):
        if not self.current_category or self._rendering:
            return
        self._rendering = True
        self._clear_cards()
        try:
            apps = self._filtered_apps()
            page, total_pages, total = self._page_info()
            page_size = self._page_size
            start = page * page_size
            end = min(start + page_size, total)
            page_apps = apps[start:end]

            cols = self._columns
            col_w = self._column_width(cols)
            half = CARD_GAP // 2
            for i in range(cols):
                self.cards_container.grid_columnconfigure(i, weight=1, uniform="hub_cols")
            for r in range(self._rows):
                self.cards_container.grid_rowconfigure(r, weight=0, minsize=CARD_HEIGHT + CARD_GAP)

            for i, app in enumerate(page_apps):
                row, col = divmod(i, cols)
                card = AppCard(self.cards_container, app, self.icon_manager, self.winget_manager, hub_view=self)
                card.set_column_width(col_w)
                card.grid(row=row, column=col, padx=half, pady=half, sticky="nsew")
                self.current_cards.append(card)

            show_start = start + 1 if total else 0
            show_end = end
            self._set_pagination_idle(page, total_pages, show_start, show_end, total)
        finally:
            self._rendering = False

    def _on_search(self, _event=None):
        if not self.current_category:
            return
        self._page_by_cat[self.current_category["id"]] = 0
        self._render_current_page()

    def load_category(self, category_data, active_btn):
        self.search_entry.delete(0, "end")
        for btn in self.category_buttons:
            btn.configure(fg_color="transparent", text_color=T.TEXT_SEC)
        active_btn.configure(fg_color=T.ELEVATED, text_color=T.ACCENT)
        self._active_category_btn = active_btn

        self.current_category = category_data
        cat_id = category_data["id"]
        self._page_by_cat[cat_id] = 0
        self._render_current_page()

    def _install_all_category(self):
        if not self.current_category:
            return
        to_install = [
            app["id"] for app in self.current_category["apps"]
            if self.winget_manager.get_app_info(app["id"]).get("status") != "installed"
        ]
        if not to_install:
            orig = self.btn_install_category.cget("text")
            self.btn_install_category.configure(text="Todo instalado")
            self.after(2000, lambda: self.btn_install_category.configure(text=orig))
            return
        self._run_install_by_ids(to_install)

    def _start_install(self):
        selected = [c for c in self.current_cards if c.checkbox.get()]
        if not selected:
            orig = self.btn_install_all.cget("text")
            self.btn_install_all.configure(text="Selecciona apps primero", fg_color=T.AMBER)
            self.after(2000, lambda: self.btn_install_all.configure(text=orig, fg_color=T.GREEN))
            return
        self._run_install_by_ids([c.app_data["id"] for c in selected], selected)

    def _run_install_by_ids(self, app_ids, selected_cards=None):
        self.btn_install_all.configure(state="disabled", text="Instalando…")
        modal = InstallProgressModal(self.winfo_toplevel(), app_ids, self.winget_manager)
        card_map = {c.app_data["id"]: c for c in (selected_cards or self.current_cards) if c.app_data["id"] in app_ids}
        for c in card_map.values():
            c.mark_installing()

        def on_progress(current, total, app_id):
            self.after(0, lambda: modal.update_progress(current, total, app_id))

        def on_log(line):
            cleaned = _clean_winget_line(line)
            if cleaned:
                self.after(0, lambda l=cleaned: modal.append_log(l))

        def on_done(results):
            for r in results:
                card = card_map.get(r["id"])
                if card:
                    self.after(0, lambda c=card, ok=r["ok"]: c.mark_done(ok))
            self.after(0, lambda: modal.finish(results))
            self.after(0, lambda: self.btn_install_all.configure(state="normal", text="Instalar seleccionados"))
            self.after(0, self._render_current_page)
            self.after(500, self._refresh_category_buttons)

        self.winget_manager.install_apps(app_ids, on_progress=on_progress, on_log=on_log, on_done=on_done)

    def uninstall_app(self, card: AppCard):
        card.status.configure(text="Desinstalando…", text_color=T.ACCENT)

        def on_done(_result):
            self.after(0, self._render_current_page)
            self.after(500, self._refresh_category_buttons)

        self.winget_manager.uninstall_app(card.app_data["id"], on_done=on_done)
