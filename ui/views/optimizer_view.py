"""Optimizer view with glassmorphism styling and live progress."""
import customtkinter as ctk
from backend.optimization_engine import OptimizationEngine, TWEAK_META, REVERTABLE
from backend.utils import request_admin_restart
from ui import theme as T
from ui.widgets import AnimatedProgressBar


class OptimizerView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=T.BG_PRIMARY)

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._all_selected = False
        self._busy = False
        self._hidden = False
        self._tweak_frames = {}
        self._tweak_status = {}
        self._revert_vars = {}
        self._checkboxes = {}

        self._engine = OptimizationEngine(
            callback_log=self._log_msg,
            on_progress=self._on_progress,
            on_tweak_status=self._on_tweak_status,
            on_done=self._on_done,
        )

        # Top
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=20)
        top.grid_columnconfigure(1, weight=1)

        self._title = T.heading(top, "Optimizaci\u00f3n de rendimiento", size=26)
        self._title.grid(row=0, column=0, sticky="w")

        self._score_lbl = ctk.CTkLabel(
            top,
            text=f"{OptimizationEngine.count_available_tweaks()} optimizaciones disponibles",
            font=T.font(14), text_color=T.GREEN,
        )
        self._score_lbl.grid(row=1, column=0, sticky="w", pady=(5, 0))

        admin_txt = "Ejecutando como administrador" if OptimizationEngine.is_admin() else "Sin admin \u2014 algunos tweaks se omitir\u00e1n"
        self._admin_lbl = ctk.CTkLabel(
            top, text=admin_txt,
            font=T.font(11), text_color=T.GREEN if OptimizationEngine.is_admin() else T.AMBER,
        )
        self._admin_lbl.grid(row=2, column=0, sticky="w", pady=(4, 0))

        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.grid(row=0, column=1, rowspan=3, sticky="e")
        if not OptimizationEngine.is_admin():
            self._btn_admin = T.btn_secondary(
                actions, "Ejecutar como admin",
                command=self._restart_as_admin,
                fg_color=T.AMBER, text_color="#1a1a1a",
            )
            self._btn_admin.pack(side="right", padx=5)
        self._btn_select = T.btn_secondary(actions, "Seleccionar todo", command=self._toggle_select_all)
        self._btn_select.pack(side="right", padx=5)
        self._btn_optimize = T.btn_primary(actions, "Aplicar tweaks", command=self._start_opt, height=44)
        self._btn_optimize.pack(side="right", padx=10)

        # Progress
        self._progress_frame = T.glass_card(self)
        self._progress_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        self._progress_frame.grid_columnconfigure(0, weight=1)
        self._animated_progress = AnimatedProgressBar(self._progress_frame, height=10)
        self._animated_progress.grid(row=0, column=0, sticky="ew", padx=15, pady=12)

        # Main area
        self._main_frame = T.glass_card(self)
        self._main_frame.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 20))
        self._main_frame.grid_rowconfigure(0, weight=1)
        self._main_frame.grid_columnconfigure(0, weight=1)
        self._main_frame.grid_columnconfigure(1, weight=1)
        self._main_frame.grid_columnconfigure(2, weight=1)

        self._options_frame = ctk.CTkScrollableFrame(
            self._main_frame, fg_color="transparent",
            scrollbar_button_color=T.BORDER,
        )
        self._options_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=20, pady=20)
        self._options_frame.grid_columnconfigure(0, weight=1)
        self._options_frame.bind("<Configure>", self._update_tooltip_wrap)
        T.theme_scrollable(self._options_frame)

        self._build_options()

        # Log panel
        self._log_frame = T.glass_card(self._main_frame, fg_color=T.INSET, corner_radius=T.RADIUS_SM)
        self._log_frame.grid(row=0, column=2, sticky="nsew", padx=(0, 20), pady=20)
        self._log_frame.grid_rowconfigure(1, weight=1)
        self._log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self._log_frame, text="Terminal (Admin)",
            font=T.font(12, "bold", mono=True), text_color=T.TEXT_SEC,
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self._log_box = ctk.CTkTextbox(
            self._log_frame, fg_color=T.INSET, text_color=T.TEXT,
            font=T.font(12, mono=True),
        )
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self._setup_log_tags()
        self._append_log("Esperando ordenes de optimizacion...\n", "default")

    def _build_options(self):
        r = 0

        def section_header(text):
            nonlocal r
            lbl = ctk.CTkLabel(
                self._options_frame, text=text,
                font=T.font(12, "bold"), text_color=T.ACCENT, anchor="w",
            )
            lbl.grid(row=r, column=0, sticky="ew", pady=(16, 4))
            r += 1

        def add_checkbox(opt_id, text, tooltip, default):
            nonlocal r
            var = ctk.BooleanVar(value=default)
            frame = T.glass_card(self._options_frame, fg_color=T.INSET, corner_radius=T.RADIUS_SM)
            frame.grid(row=r, column=0, sticky="ew", pady=4, padx=2)
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_columnconfigure(1, weight=0)
            cb = ctk.CTkCheckBox(
                frame, text=text, variable=var, font=T.font(13, "bold"),
                text_color=T.TEXT, fg_color=T.GREEN, hover_color=T.GREEN_HOVER,
                checkmark_color="#FFFFFF", width=20,
            )
            cb.grid(row=0, column=0, sticky="w", padx=12, pady=8)
            status_lbl = ctk.CTkLabel(frame, text="", font=T.font(14), width=24)
            status_lbl.grid(row=0, column=1, padx=(0, 10))
            tip_lbl = ctk.CTkLabel(
                frame, text=tooltip,
                font=T.font(11), text_color=T.TEXT_SEC, anchor="w", wraplength=360,
            )
            tip_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=36, pady=(0, 8))
            self._checkboxes[opt_id] = var
            self._tweak_frames[opt_id] = frame
            self._tweak_status[opt_id] = status_lbl
            frame._tip_lbl = tip_lbl
            r += 1

        section_header("SISTEMA BASE")
        add_checkbox("restore_point", "Punto de restauraci\u00f3n previo", "Recomendado antes de tweaks agresivos.", True)
        add_checkbox("telemetry", "Bloquear telemetr\u00eda principal", "DiagTrack y dmwappush. Verificado tras aplicar.", True)
        add_checkbox("telemetry_extra", "Servicios telemetr\u00eda adicionales", "WerSvc, PcaSvc y relacionados (lista curada).", False)
        add_checkbox("power_plan", "Plan Ultimate Performance", "Plan oculto de m\u00e1ximo rendimiento.", True)
        add_checkbox("power_fine", "Ajustes finos de energ\u00eda", "Timeout de disco y USB selective suspend.", False)
        add_checkbox("temp", "Limpieza temporal profunda", "%TEMP%, Prefetch, cach\u00e9 WU y papelera.", True)
        add_checkbox("visual_effects", "Efectos visuales rendimiento", "Animaciones y transparencias desactivadas.", False)
        add_checkbox("disk_optimize", "Optimizaci\u00f3n de discos", "TRIM en SSD, defrag en HDD.", False)
        add_checkbox("standby_ram", "Vaciar standby list", "Libera RAM en cach\u00e9 standby (requiere admin).", False)
        add_checkbox("fast_startup", "Arranque r\u00e1pido", "Elimina delay de inicio de Windows.", False)
        add_checkbox("tips_suggestions", "Tips y sugerencias off", "Desactiva notificaciones de sugerencias de Windows.", False)
        add_checkbox("hibernate_off", "Desactivar hibernaci\u00f3n", "Libera espacio en disco (hiberfil.sys).", False)
        add_checkbox("ntfs_optimize", "NTFS sin last access", "Reduce I/O en SSD desactivando timestamp de acceso.", False)
        add_checkbox("background_apps", "Apps segundo plano off", "Impide que apps UWP consuman recursos en background.", False)
        add_checkbox("widgets_off", "Widgets Windows off", "Oculta panel de widgets en barra de tareas.", False)

        section_header("GAMING & GPU")
        add_checkbox("gaming", "Tweaks gaming (GameBar/DVR)", "Reduce input lag.", True)
        add_checkbox("game_mode", "Game Mode Windows", "Prioriza recursos al juego.", True)
        add_checkbox("hags", "HAGS", "GPU scheduling hardware. Reinicio.", False)
        add_checkbox("mmcss", "MMCSS prioridad juegos", "GPU/CPU priority m\u00e1xima.", True)
        add_checkbox("mouse_precision", "Mouse 1:1", "Sin aceleraci\u00f3n.", True)
        add_checkbox("vbs", "[!] Desactivar VBS/HVCI", "M\u00e1s FPS, menos seguridad kernel.", False)
        add_checkbox("fullscreen_opt", "Fullscreen optimizations off", "Desactiva optimizaciones FSE que causan stutter.", False)

        section_header("NICHO VERIFICADO")
        add_checkbox("core_parking", "Core parking off", "Todos los n\u00facleos activos.", False)
        add_checkbox("windowed_opt", "Windowed optimizations", "Flip model en ventana.", False)
        add_checkbox("auto_maintenance", "Mantenimiento auto off", "Evita scans en gaming.", False)
        add_checkbox("power_throttling", "Power throttling off", "Sin l\u00edmite en background.", False)
        add_checkbox("delivery_opt", "Delivery Optimization off", "Sin P2P de updates.", True)

        section_header("RED & SERVICIOS")
        add_checkbox("network", "Flush DNS + Winsock", "Purga DNS y resetea TCP/IP.", False)
        add_checkbox("dns_custom", "DNS 8.8.8.8 / 1.1.1.1", "Flush + DNS custom. Revertible a DHCP.", False)
        add_checkbox("tcp_optimize", "TCP baja latencia", "Nagle off + ajustes netsh para gaming/red.", False)
        add_checkbox("services", "SysMain / WSearch off", "Recomendado en SSD.", False)
        add_checkbox("startup", "Inicio de terceros off", "Lista y deshabilita entradas no Microsoft.", False)

        self._options_row = r
        self._revert_container = ctk.CTkFrame(self._options_frame, fg_color="transparent")
        self._revert_container.grid(row=r, column=0, sticky="ew")
        self._revert_container.grid_columnconfigure(0, weight=1)
        self._build_revert_section()

    def on_show(self):
        self._hidden = False
        self.update_idletasks()
        T.refresh_scroll_region(self._options_frame)

    def on_hide(self):
        self._hidden = True

    def _clear_revert(self):
        for child in self._revert_container.winfo_children():
            child.destroy()
        self._revert_vars = {}

    def _build_revert_section(self):
        self._clear_revert()
        applied = self._engine.get_applied_tweaks()
        revertable = [t for t in applied if t in REVERTABLE]
        if not revertable:
            return
        r = 0

        def section_header(text):
            nonlocal r
            lbl = ctk.CTkLabel(
                self._revert_container, text=text,
                font=T.font(12, "bold"), text_color=T.ACCENT, anchor="w",
            )
            lbl.grid(row=r, column=0, sticky="ew", pady=(16, 4))
            r += 1

        section_header("REVERTIR")
        for tid in revertable:
            var = ctk.BooleanVar(value=False)
            frame = T.glass_card(self._revert_container, fg_color=T.INSET, border_color=T.RED)
            frame.grid(row=r, column=0, sticky="ew", pady=4, padx=2)
            lbl = OptimizationEngine.get_label(tid)
            ctk.CTkCheckBox(
                frame, text=f"Revertir: {lbl}", variable=var,
                font=T.font(13, "bold"), text_color=T.RED, fg_color=T.RED,
            ).pack(anchor="w", padx=12, pady=8)
            self._revert_vars[tid] = var
            r += 1
        T.btn_secondary(
            self._revert_container, "Revertir seleccionados",
            command=self._start_revert, fg_color=T.RED, text_color=T.TEXT,
        ).grid(row=r, column=0, sticky="ew", pady=(8, 4))

    def _setup_log_tags(self):
        tb = self._log_box._textbox
        tb.tag_configure("ok", foreground=T.GREEN)
        tb.tag_configure("error", foreground=T.RED)
        tb.tag_configure("warn", foreground=T.AMBER)
        tb.tag_configure("default", foreground=T.TEXT)

    def _append_log(self, message: str, tag: str = "default"):
        self._log_box.configure(state="normal")
        self._log_box._textbox.insert("end", message, tag)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _detect_tag(self, msg: str) -> str:
        lower = msg.lower()
        if "[error]" in lower:
            return "error"
        if "[ok]" in lower or "exitosamente" in lower:
            return "ok"
        if "[warn]" in lower or "[!]" in lower:
            return "warn"
        return "default"

    def _log_msg(self, message):
        if not self._hidden:
            self.after(0, self._append_log_ui, message)

    def _append_log_ui(self, message):
        self._append_log(message + "\n", self._detect_tag(message))

    def _on_progress(self, done, total, tweak_id, label):
        if not self._hidden:
            self.after(0, self._update_progress, done, total, tweak_id, label)

    def _update_progress(self, done, total, tweak_id, label):
        if total == 0:
            self._animated_progress.set_indeterminate(True, "Preparando\u2026")
            return
        if done == 0 and total > 0:
            self._animated_progress.set_indeterminate(False)
        pct = done / total if total else 0
        step = f"Aplicando {done} de {total}"
        if label and tweak_id:
            step += f" \u2014 {label}"
        self._animated_progress.set_progress(pct, text=step, state="running")

    def _on_tweak_status(self, tweak_id, status):
        if self._hidden:
            return
        icons = {"running": "\u2026", "ok": "\u2713", "error": "\u2717", "skipped": "\u2212"}
        icon = icons.get(status, "")
        if tweak_id in self._tweak_status:
            self.after(0, lambda: self._tweak_status[tweak_id].configure(text=icon))

    def _on_done(self, results):
        if not self._hidden:
            self.after(0, lambda: self._finish_job(results))

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._btn_optimize.configure(
            state="disabled" if busy else "normal",
            text="Optimizando\u2026" if busy else "Aplicar tweaks",
        )

    def _finish_job(self, results):
        if not results:
            self._set_busy(False)
            self._animated_progress.reset()
            return
        ok_n = sum(1 for r in results if r.status == "ok")
        total = len(results)
        self._animated_progress.finish(
            ok_n > 0,
            text=f"Finalizado: {ok_n}/{total} exitosos",
            on_complete=lambda: (self._set_busy(False), self._build_revert_section()),
        )

    def _start_opt(self):
        if self._busy:
            return
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        for lbl in self._tweak_status.values():
            lbl.configure(text="")
        self._set_busy(True)
        self._animated_progress.reset()
        self._animated_progress.set_indeterminate(True, "Iniciando optimizaci\u00f3n\u2026")
        selected = {oid: var.get() for oid, var in self._checkboxes.items()}
        self._engine.optimize_all(selected)

    def _start_revert(self):
        if self._busy:
            return
        selected = [tid for tid, var in self._revert_vars.items() if var.get()]
        if not selected:
            self._log_msg("[WARN] Selecciona tweaks para revertir.")
            return
        self._set_busy(True)
        self._animated_progress.reset()
        self._animated_progress.set_indeterminate(True, "Revirtiendo\u2026")
        self._engine.revert_tweaks(selected)

    def _toggle_select_all(self):
        self._all_selected = not self._all_selected
        for var in self._checkboxes.values():
            var.set(self._all_selected)
        self._btn_select.configure(
            text="Deseleccionar todo" if self._all_selected else "Seleccionar todo",
        )

    def _restart_as_admin(self):
        request_admin_restart()

    def _update_tooltip_wrap(self, _=None):
        w = self._options_frame.winfo_width()
        wrap = max(200, w - 80)
        for frame in self._tweak_frames.values():
            if hasattr(frame, "_tip_lbl"):
                frame._tip_lbl.configure(wraplength=wrap)
