import customtkinter as ctk
from backend.optimization_engine import OptimizationEngine, TWEAK_META, REVERTABLE
from backend.utils import request_admin_restart
from ui import theme as T
from ui.widgets.animated_progress import AnimatedProgressBar


class OptimizerView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=T.BG)

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._all_selected = False
        self._busy = False
        self.tweak_frames: dict[str, ctk.CTkFrame] = {}
        self.tweak_status: dict[str, ctk.CTkLabel] = {}
        self.revert_vars: dict[str, ctk.BooleanVar] = {}
        self._theme_widgets: list = []

        self.engine = OptimizationEngine(
            callback_log=self.log_message,
            on_progress=self._on_progress,
            on_tweak_status=self._on_tweak_status,
            on_done=self._on_done,
        )

        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        self.top_frame.grid_columnconfigure(1, weight=1)

        self.title_label = T.heading(self.top_frame, "Optimización de rendimiento", size=26)
        self.title_label.grid(row=0, column=0, sticky="w")

        self.score_label = ctk.CTkLabel(
            self.top_frame,
            text=f"{OptimizationEngine.count_available_tweaks()} optimizaciones disponibles",
            font=T.font(14), text_color=T.GREEN,
        )
        self.score_label.grid(row=1, column=0, sticky="w", pady=(5, 0))

        admin_txt = "Ejecutando como administrador" if OptimizationEngine.is_admin() else "Sin admin — algunos tweaks se omitirán"
        self.admin_lbl = ctk.CTkLabel(
            self.top_frame, text=admin_txt,
            font=T.font(11), text_color=T.GREEN if OptimizationEngine.is_admin() else T.AMBER,
        )
        self.admin_lbl.grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.actions_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.actions_frame.grid(row=0, column=1, rowspan=3, sticky="e")
        if not OptimizationEngine.is_admin():
            self.btn_admin = T.btn_secondary(
                self.actions_frame, "Ejecutar como admin",
                command=self._restart_as_admin, fg_color=T.AMBER, text_color="#1a1a1a",
            )
            self.btn_admin.pack(side="right", padx=5)
        self.btn_select_all = T.btn_secondary(self.actions_frame, "Seleccionar todo", command=self.toggle_select_all)
        self.btn_select_all.pack(side="right", padx=5)
        self.btn_optimize = T.btn_primary(self.actions_frame, "Aplicar tweaks", command=self.start_optimization, height=44)
        self.btn_optimize.pack(side="right", padx=10)

        self.progress_frame = T.card(self)
        self.progress_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.animated_progress = AnimatedProgressBar(self.progress_frame, height=10)
        self.animated_progress.grid(row=0, column=0, sticky="ew", padx=15, pady=12)

        self.main_frame = T.card(self, corner_radius=T.RADIUS_MD)
        self.main_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(2, weight=1)

        self.options_frame = ctk.CTkScrollableFrame(
            self.main_frame, fg_color=T.BG, bg_color=T.BG, scrollbar_button_color=T.BORDER,
        )
        self.options_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=20, pady=20)
        self.options_frame.grid_columnconfigure(0, weight=1)
        self.options_frame.bind("<Configure>", self._update_tooltip_wrap)
        T.theme_scrollable(self.options_frame, fg=T.BG, canvas_bg=T.BG)

        self.checkboxes: dict[str, ctk.BooleanVar] = {}
        self._build_options()

        self.log_frame = T.card(self.main_frame, fg_color=T.INSET, corner_radius=T.RADIUS_SM)
        self.log_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 20), pady=20)
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        self.log_title = ctk.CTkLabel(
            self.log_frame, text="Terminal (Admin)",
            font=T.font(12, "bold", mono=True), text_color=T.TEXT_SEC,
        )
        self.log_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.log_textbox = ctk.CTkTextbox(
            self.log_frame, fg_color=T.LOG_BG, text_color=T.TEXT,
            font=T.font(12, mono=True),
        )
        self.log_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self._setup_log_tags()
        self._append_log("Esperando ordenes de optimizacion...\n", "default")

    def _build_options(self):
        r = 0

        def section_header(text, row):
            lbl = ctk.CTkLabel(self.options_frame, text=text, font=T.font(12, "bold"), text_color=T.ACCENT, anchor="w")
            lbl.grid(row=row, column=0, sticky="ew", pady=(16, 4))

        def add_checkbox(opt_id, text, tooltip, default, row):
            var = ctk.BooleanVar(value=default)
            frame = T.card(self.options_frame, fg_color=T.INSET, corner_radius=T.RADIUS_SM)
            frame.grid(row=row, column=0, sticky="ew", pady=4, padx=2)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_columnconfigure(1, weight=0)
            cb = ctk.CTkCheckBox(
                frame, text=text, variable=var, font=T.font(13, "bold"),
                text_color=T.TEXT, fg_color=T.GREEN, hover_color=T.GREEN_HOVER,
                checkmark_color="#FFFFFF", width=20,
            )
            cb.grid(row=0, column=0, sticky="w", padx=12, pady=8)
            status = ctk.CTkLabel(frame, text="", font=T.font(14), width=24)
            status.grid(row=0, column=1, padx=(0, 10))
            tip_lbl = ctk.CTkLabel(
                frame, text=tooltip, font=T.font(11), text_color=T.TEXT_SEC, anchor="w", wraplength=360,
            )
            tip_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=36, pady=(0, 8))
            self.checkboxes[opt_id] = var
            self.tweak_frames[opt_id] = frame
            self.tweak_status[opt_id] = status
            frame._tip_lbl = tip_lbl

        section_header("SISTEMA BASE", r); r += 1
        add_checkbox("restore_point", "Punto de restauración previo",
                     "Recomendado antes de tweaks agresivos.", True, r); r += 1
        add_checkbox("telemetry", "Bloquear telemetría principal",
                     "DiagTrack y dmwappush. Verificado tras aplicar.", True, r); r += 1
        add_checkbox("telemetry_extra", "Servicios telemetría adicionales",
                     "WerSvc, PcaSvc y relacionados (lista curada).", False, r); r += 1
        add_checkbox("power_plan", "Plan Ultimate Performance", "Plan oculto de máximo rendimiento.", True, r); r += 1
        add_checkbox("power_fine", "Ajustes finos de energía",
                     "Timeout de disco y USB selective suspend.", False, r); r += 1
        add_checkbox("temp", "Limpieza temporal profunda",
                     "%TEMP%, Prefetch, caché WU y papelera.", True, r); r += 1
        add_checkbox("visual_effects", "Efectos visuales rendimiento",
                     "Animaciones y transparencias desactivadas.", False, r); r += 1
        add_checkbox("disk_optimize", "Optimización de discos",
                     "TRIM en SSD, defrag en HDD.", False, r); r += 1
        add_checkbox("standby_ram", "Vaciar standby list",
                     "Libera RAM en caché standby (requiere admin).", False, r); r += 1
        add_checkbox("fast_startup", "Arranque rápido",
                     "Elimina delay de inicio de Windows.", False, r); r += 1
        add_checkbox("tips_suggestions", "Tips y sugerencias off",
                     "Desactiva notificaciones de sugerencias de Windows.", False, r); r += 1
        add_checkbox("hibernate_off", "Desactivar hibernación",
                     "Libera espacio en disco (hiberfil.sys).", False, r); r += 1
        add_checkbox("ntfs_optimize", "NTFS sin last access",
                     "Reduce I/O en SSD desactivando timestamp de acceso.", False, r); r += 1
        add_checkbox("background_apps", "Apps segundo plano off",
                     "Impide que apps UWP consuman recursos en background.", False, r); r += 1
        add_checkbox("widgets_off", "Widgets Windows off",
                     "Oculta panel de widgets en barra de tareas.", False, r); r += 1

        section_header("GAMING & GPU", r); r += 1
        add_checkbox("gaming", "Tweaks gaming (GameBar/DVR)", "Reduce input lag.", True, r); r += 1
        add_checkbox("game_mode", "Game Mode Windows", "Prioriza recursos al juego.", True, r); r += 1
        add_checkbox("hags", "HAGS", "GPU scheduling hardware. Reinicio.", False, r); r += 1
        add_checkbox("mmcss", "MMCSS prioridad juegos", "GPU/CPU priority máxima.", True, r); r += 1
        add_checkbox("mouse_precision", "Mouse 1:1", "Sin aceleración.", True, r); r += 1
        add_checkbox("vbs", "[!] Desactivar VBS/HVCI", "Más FPS, menos seguridad kernel.", False, r); r += 1
        add_checkbox("fullscreen_opt", "Fullscreen optimizations off",
                     "Desactiva optimizaciones FSE que causan stutter.", False, r); r += 1

        section_header("NICHO VERIFICADO", r); r += 1
        add_checkbox("core_parking", "Core parking off", "Todos los núcleos activos.", False, r); r += 1
        add_checkbox("windowed_opt", "Windowed optimizations", "Flip model en ventana.", False, r); r += 1
        add_checkbox("auto_maintenance", "Mantenimiento auto off", "Evita scans en gaming.", False, r); r += 1
        add_checkbox("power_throttling", "Power throttling off", "Sin límite en background.", False, r); r += 1
        add_checkbox("delivery_opt", "Delivery Optimization off", "Sin P2P de updates.", True, r); r += 1

        section_header("RED & SERVICIOS", r); r += 1
        add_checkbox("network", "Flush DNS + Winsock", "Purga DNS y resetea TCP/IP.", False, r); r += 1
        add_checkbox("dns_custom", "DNS 8.8.8.8 / 1.1.1.1",
                     "Flush + DNS custom. Revertible a DHCP.", False, r); r += 1
        add_checkbox("tcp_optimize", "TCP baja latencia",
                     "Nagle off + ajustes netsh para gaming/red.", False, r); r += 1
        add_checkbox("services", "SysMain / WSearch off", "Recomendado en SSD.", False, r); r += 1
        add_checkbox("startup", "Inicio de terceros off",
                     "Lista y deshabilita entradas no Microsoft.", False, r); r += 1

        self._options_row = r
        self.revert_container = ctk.CTkFrame(self.options_frame, fg_color="transparent")
        self.revert_container.grid(row=r, column=0, sticky="ew")
        self.revert_container.grid_columnconfigure(0, weight=1)
        self._build_revert_section()

    def on_show(self):
        self.update_idletasks()
        T.refresh_scroll_region(self.options_frame)
        self.options_frame.event_generate("<Configure>")

    def on_hide(self):
        pass

    def _clear_revert_section(self):
        for child in self.revert_container.winfo_children():
            child.destroy()
        self.revert_vars = {}

    def _build_revert_section(self):
        self._clear_revert_section()
        applied = self.engine.get_applied_tweaks()
        revertable = [t for t in applied if t in REVERTABLE]
        if not revertable:
            return
        r = 0

        def section_header(text, row):
            lbl = ctk.CTkLabel(self.revert_container, text=text, font=T.font(12, "bold"), text_color=T.ACCENT, anchor="w")
            lbl.grid(row=row, column=0, sticky="ew", pady=(16, 4))

        section_header("REVERTIR", r); r += 1
        for tid in revertable:
            var = ctk.BooleanVar(value=False)
            frame = T.card(self.revert_container, fg_color=T.INSET, border_color=T.RED)
            frame.grid(row=r, column=0, sticky="ew", pady=4, padx=2)
            lbl = OptimizationEngine.get_label(tid)
            ctk.CTkCheckBox(
                frame, text=f"Revertir: {lbl}", variable=var,
                font=T.font(13, "bold"), text_color=T.RED, fg_color=T.RED,
            ).pack(anchor="w", padx=12, pady=8)
            self.revert_vars[tid] = var
            r += 1
        self.btn_revert = T.btn_secondary(
            self.revert_container, "Revertir seleccionados",
            command=self.start_revert, fg_color=T.RED, text_color=T.TEXT,
        )
        self.btn_revert.grid(row=r, column=0, sticky="ew", pady=(8, 4))

    def apply_theme(self):
        self.configure(fg_color=T.BG)
        self.progress_frame.configure(fg_color=T.SURFACE, border_color=T.BORDER)
        self.main_frame.configure(fg_color=T.SURFACE, border_color=T.BORDER)
        self.log_frame.configure(fg_color=T.INSET, border_color=T.BORDER)
        T.theme_scrollable(self.options_frame, fg=T.BG, canvas_bg=T.BG)
        self.title_label.configure(text_color=T.TEXT)
        self.score_label.configure(text_color=T.GREEN)
        self.admin_lbl.configure(
            text_color=T.GREEN if OptimizationEngine.is_admin() else T.AMBER,
        )
        self.log_title.configure(text_color=T.TEXT_SEC)
        self.log_textbox.configure(text_color=T.TEXT, fg_color=T.LOG_BG)
        self._setup_log_tags()
        self.animated_progress.apply_theme()
        for frame in self.tweak_frames.values():
            frame.configure(fg_color=T.INSET, border_color=T.BORDER)
        for child in self.revert_container.winfo_children():
            if isinstance(child, ctk.CTkFrame):
                child.configure(fg_color=T.INSET, border_color=T.RED)

    def _setup_log_tags(self):
        tb = self.log_textbox._textbox
        tb.tag_configure("ok", foreground=T.GREEN)
        tb.tag_configure("error", foreground=T.RED)
        tb.tag_configure("warn", foreground=T.AMBER)
        tb.tag_configure("default", foreground=T.TEXT)

    def _append_log(self, message: str, tag: str = "default"):
        self.log_textbox.configure(state="normal")
        self.log_textbox._textbox.insert("end", message, tag)
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def _detect_log_tag(self, message: str) -> str:
        lower = message.lower()
        if "[error]" in lower:
            return "error"
        if "[ok]" in lower or "exitosamente" in lower:
            return "ok"
        if "[warn]" in lower or "[!]" in lower:
            return "warn"
        return "default"

    def _update_tooltip_wrap(self, event=None):
        w = self.options_frame.winfo_width()
        wrap = max(200, w - 80)
        for frame in self.tweak_frames.values():
            if hasattr(frame, "_tip_lbl"):
                frame._tip_lbl.configure(wraplength=wrap)

    def toggle_select_all(self):
        self._all_selected = not self._all_selected
        for var in self.checkboxes.values():
            var.set(self._all_selected)
        self.btn_select_all.configure(text="Deseleccionar todo" if self._all_selected else "Seleccionar todo")

    def _restart_as_admin(self):
        request_admin_restart()

    def log_message(self, message):
        self.after(0, self._append_log_ui, message)

    def _append_log_ui(self, message):
        self._append_log(message + "\n", self._detect_log_tag(message))

    def _on_progress(self, done, total, tweak_id, label):
        self.after(0, self._update_progress, done, total, tweak_id, label)

    def _update_progress(self, done, total, tweak_id, label):
        if total == 0:
            self.animated_progress.set_indeterminate(True, "Preparando…")
            return
        if done == 0 and total > 0:
            self.animated_progress.set_indeterminate(False)
        pct = done / total if total else 0
        step = f"Aplicando {done} de {total}"
        if label and tweak_id:
            step += f" — {label}"
        self.animated_progress.set_progress(pct, text=step, state="running")

    def _on_tweak_status(self, tweak_id, status):
        icons = {"running": "…", "ok": "✓", "error": "✗", "skipped": "−"}
        icon = icons.get(status, "")
        if tweak_id in self.tweak_status:
            self.after(0, lambda: self.tweak_status[tweak_id].configure(text=icon))

    def _on_done(self, results):
        self.after(0, lambda: self._finish_job(results))

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.btn_optimize.configure(state="disabled" if busy else "normal",
                                    text="Optimizando…" if busy else "Aplicar tweaks")

    def _finish_job(self, results):
        if not results:
            self._set_busy(False)
            self.animated_progress.reset()
            return
        ok = all(r.status == "ok" for r in results)
        any_ok = any(r.status == "ok" for r in results)
        total = len(results)
        ok_n = sum(1 for r in results if r.status == "ok")
        self.animated_progress.finish(
            any_ok,
            text=f"Finalizado: {ok_n}/{total} exitosos",
            on_complete=lambda: (self._set_busy(False), self._build_revert_section()),
        )

    def start_optimization(self):
        if self._busy:
            return
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")
        for lbl in self.tweak_status.values():
            lbl.configure(text="")
        self._set_busy(True)
        self.animated_progress.reset()
        self.animated_progress.set_indeterminate(True, "Iniciando optimización…")

        selected = {opt_id: var.get() for opt_id, var in self.checkboxes.items()}
        self.engine.optimize_all(selected)

    def start_revert(self):
        if self._busy:
            return
        selected = [tid for tid, var in self.revert_vars.items() if var.get()]
        if not selected:
            self.log_message("[WARN] Selecciona tweaks para revertir.")
            return
        self._set_busy(True)
        self.animated_progress.reset()
        self.animated_progress.set_indeterminate(True, "Revirtiendo…")
        self.engine.revert_tweaks(selected)
