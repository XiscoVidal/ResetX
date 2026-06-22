import customtkinter as ctk
import tkinter as tk
from collections import deque
from backend.system_metrics import SystemMetrics
from backend.utils import get_base_path
from ui import theme as T
from PIL import Image
import os

HISTORY_LEN = 30  # 30 samples × 2s = 60s


class Sparkline(tk.Canvas):
    def __init__(self, master, color=T.ACCENT, bg=T.SURFACE, height=28, **kwargs):
        super().__init__(master, height=height, bg=bg, highlightthickness=0, **kwargs)
        self.color = color
        self._data: deque = deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.bind("<Configure>", lambda e: self._draw())

    def push(self, value: float):
        self._data.append(max(0, min(100, value)))
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10:
            return
        data = list(self._data)
        if not data:
            return
        mx = max(data) or 1
        step = w / max(len(data) - 1, 1)
        pts = []
        for i, v in enumerate(data):
            x = i * step
            y = h - (v / mx) * (h - 4) - 2
            pts.extend([x, y])
        if len(pts) >= 4:
            self.create_line(pts, fill=self.color, width=2, smooth=True)


class CircularProgress(tk.Canvas):
    def __init__(self, master, color=T.ACCENT, bg_color=T.BG, text_color=T.TEXT, title="", **kwargs):
        super().__init__(master=master, width=1, height=1, bg=bg_color, highlightthickness=0, **kwargs)
        self.color = color
        self.bg_color = bg_color
        self.text_color = text_color
        self.title = title
        self._pct = 0
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if hasattr(self, "_resize_timer"):
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(20, lambda w=event.width, h=event.height: self._redraw(w, h))

    def _redraw(self, w, h):
        self.delete("all")
        if w < 20 or h < 20:
            return
        pad = int(min(w, h) * 0.12)
        s = min(w, h) - pad * 2
        t = max(8, s // 10)
        ox = (w - s) // 2
        oy = (h - s) // 2
        font_pct = max(14, int(s * 0.22))
        font_title = max(9, int(s * 0.09))
        x1, y1 = ox + t, oy + t
        x2, y2 = ox + s - t, oy + s - t
        self.create_oval(x1, y1, x2, y2, outline=T.ELEVATED, width=t)
        if self._pct > 0:
            self.create_arc(x1, y1, x2, y2, start=90, extent=-(self._pct / 100) * 360,
                            outline=self.color, width=t, style="arc")
        cx, cy = w / 2, h / 2
        self.create_text(cx, cy - s * 0.05, text=f"{int(self._pct)}%",
                         fill=self.text_color, font=("Inter", font_pct, "bold"))
        self.create_text(cx, cy + s * 0.18, text=self.title.upper(),
                         fill=T.TEXT_SEC, font=(T.FONT_UI, font_title, "bold"))

    def draw_arc(self, percentage):
        self._pct = percentage
        w, h = self.winfo_width(), self.winfo_height()
        if w > 1 and h > 1:
            self._redraw(w, h)


class SpecCard(ctk.CTkFrame):
    def __init__(self, master, icon, title, value, sub_value="", color=T.ACCENT):
        super().__init__(master, fg_color=T.SURFACE, border_color=T.BORDER, border_width=1, corner_radius=T.RADIUS_MD)
        self.grid_columnconfigure(1, weight=1)
        self._accent_color = color
        self._default_border = T.BORDER

        if isinstance(icon, str):
            self.icon_label = ctk.CTkLabel(self, text=icon, font=ctk.CTkFont(size=36), text_color=color)
        else:
            self.icon_label = ctk.CTkLabel(self, text="", image=icon)
        self.icon_label.grid(row=0, column=0, rowspan=3, padx=(20, 15), pady=20)

        self.title_label = ctk.CTkLabel(self, text=title, font=T.font(11, "bold"), text_color=T.TEXT_SEC)
        self.title_label.grid(row=0, column=1, sticky="sw", padx=(0, 20), pady=(15, 2))
        self.val_label = ctk.CTkLabel(self, text=value, font=T.font(15, "bold"), text_color=T.TEXT)
        self.val_label.grid(row=1, column=1, sticky="nw", padx=(0, 20))
        self.sub_label = ctk.CTkLabel(self, text=sub_value, font=T.font(11), text_color=T.TEXT_SEC)
        self.sub_label.grid(row=2, column=1, sticky="nw", padx=(0, 20), pady=(0, 15))

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)

    def _on_enter(self, e):
        self.configure(border_color=self._accent_color)

    def _on_leave(self, e):
        self.configure(border_color=self._default_border)

    def update_values(self, value, sub_value="", title=None):
        self.val_label.configure(text=value)
        self.sub_label.configure(text=sub_value)
        if title:
            self.title_label.configure(text=title)


class TelemetryBar(ctk.CTkFrame):
    def __init__(self, master, title, color):
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(1, weight=1)
        self.title_lbl = ctk.CTkLabel(self, text=title, font=T.font(12, "bold"), text_color=T.TEXT_SEC, width=105, anchor="w")
        self.title_lbl.grid(row=0, column=0, sticky="w", padx=(0, 15))
        self.bar = ctk.CTkProgressBar(self, height=6, progress_color=color, fg_color=T.ELEVATED, corner_radius=3)
        self.bar.grid(row=0, column=1, sticky="ew", padx=(0, 15))
        self.bar.set(0)
        self.val_lbl = ctk.CTkLabel(self, text="0.0", font=T.font(13, "bold", mono=True), text_color=T.TEXT, width=95, anchor="e")
        self.val_lbl.grid(row=0, column=2, sticky="e")

    def update_bar(self, percentage, text_value):
        self.bar.set(percentage)
        self.val_lbl.configure(text=text_value)


class DashboardView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=T.BG, corner_radius=0)

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._disks_built = False
        self._power_synced = False
        self._stacked_layout = False

        self._drive_usage_cache = {}
        self._drive_usage_tick = 0

        self.top_frame = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 5))
        self.top_frame.grid_columnconfigure(1, weight=1)

        self.title_label = T.heading(self.top_frame, "Dashboard", size=30)
        self.title_label.grid(row=0, column=0, sticky="w")

        self.uptime_label = ctk.CTkLabel(self.top_frame, text="Uptime: —", font=T.font(12, mono=True), text_color=T.TEXT_SEC)
        self.uptime_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.health_frame = T.card(self.top_frame, fg_color=T.ELEVATED, border_color=T.ACCENT)
        self.health_frame.grid(row=0, column=2, rowspan=2, sticky="e")
        self.health_label = ctk.CTkLabel(self.health_frame, text="Evaluando sistema…", font=T.font(15, "bold"))
        self.health_label.pack(padx=20, pady=8)

        self.specs_frame = ctk.CTkFrame(self, fg_color=T.BG, corner_radius=0)
        self.specs_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        self.specs_frame.grid_columnconfigure((0, 1, 2), weight=1)

        base_dir = get_base_path()
        self.cpu_img = ctk.CTkImage(light_image=Image.open(os.path.join(base_dir, "assets", "icons", "cpu.png")),
                                     dark_image=Image.open(os.path.join(base_dir, "assets", "icons", "cpu.png")), size=(36, 36))
        self.gpu_img = ctk.CTkImage(light_image=Image.open(os.path.join(base_dir, "assets", "icons", "gpu.png")),
                                     dark_image=Image.open(os.path.join(base_dir, "assets", "icons", "gpu.png")), size=(36, 36))
        self.ram_img = ctk.CTkImage(light_image=Image.open(os.path.join(base_dir, "assets", "icons", "ram.png")),
                                     dark_image=Image.open(os.path.join(base_dir, "assets", "icons", "ram.png")), size=(36, 36))
        self.disk_img = ctk.CTkImage(light_image=Image.open(os.path.join(base_dir, "assets", "icons", "disk.png")),
                                      dark_image=Image.open(os.path.join(base_dir, "assets", "icons", "disk.png")), size=(36, 36))

        self.cpu_card = SpecCard(self.specs_frame, self.cpu_img, "PROCESADOR", "Cargando…", sub_value="…", color=T.ACCENT)
        self.cpu_card.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.gpu_card = SpecCard(self.specs_frame, self.gpu_img, "GRÁFICA", "Cargando…", sub_value="…", color=T.GREEN)
        self.gpu_card.grid(row=0, column=1, sticky="ew", padx=5)
        self.ram_card = SpecCard(self.specs_frame, self.ram_img, "MEMORIA RAM", "Cargando…", sub_value="…", color=T.PURPLE)
        self.ram_card.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        self.disk_section = T.card(self, corner_radius=T.RADIUS_MD)
        self.disk_section.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 5))
        self.disk_section.grid_columnconfigure(0, weight=1)
        _disk_header = ctk.CTkFrame(self.disk_section, fg_color="transparent", corner_radius=0)
        _disk_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 4))
        T.section_label(_disk_header, "ALMACENAMIENTO").pack(side="left")
        self.disk_cards_frame = ctk.CTkFrame(self.disk_section, fg_color="transparent", corner_radius=0)
        self.disk_cards_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.disk_cards = []
        _ph = SpecCard(self.disk_cards_frame, self.disk_img, "DISCO", "Cargando…", sub_value="Detectando…", color=T.ORANGE)
        _ph.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.disk_cards = [_ph]

        self.metrics_container = T.card(self, corner_radius=T.RADIUS_LG)
        self.metrics_container.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.metrics_container.grid_rowconfigure(0, weight=1)
        self.metrics_container.grid_rowconfigure(1, weight=0)
        self.metrics_container.grid_columnconfigure(0, weight=3)
        self.metrics_container.grid_columnconfigure(1, weight=2)
        self.metrics_container.bind("<Configure>", self._on_metrics_resize)

        self.circle_frame = ctk.CTkFrame(self.metrics_container, fg_color=T.BG, corner_radius=0)
        self.circle_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        self.circle_frame.grid_columnconfigure((0, 1), weight=1)
        self.circle_frame.grid_rowconfigure((0, 1), weight=1)

        self.cpu_progress = CircularProgress(self.circle_frame, title="CPU", color=T.ACCENT, bg_color=T.BG)
        self.cpu_progress.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.gpu_progress = CircularProgress(self.circle_frame, title="GPU", color=T.GREEN, bg_color=T.BG)
        self.gpu_progress.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.ram_progress = CircularProgress(self.circle_frame, title="RAM", color=T.PURPLE, bg_color=T.BG)
        self.ram_progress.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.disk_progress = CircularProgress(self.circle_frame, title="Disco", color=T.ORANGE, bg_color=T.BG)
        self.disk_progress.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        self.spark_cpu_frame = ctk.CTkFrame(self.circle_frame, fg_color=T.SURFACE, corner_radius=T.RADIUS_SM, height=36)
        self.spark_cpu_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        T.section_label(self.spark_cpu_frame, "CPU 60s").pack(side="left", padx=8)
        self.spark_cpu = Sparkline(self.spark_cpu_frame, color=T.ACCENT)
        self.spark_cpu.pack(fill="x", expand=True, padx=8, pady=4)

        self.spark_ram_frame = ctk.CTkFrame(self.circle_frame, fg_color=T.SURFACE, corner_radius=T.RADIUS_SM, height=36)
        self.spark_ram_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        T.section_label(self.spark_ram_frame, "RAM 60s").pack(side="left", padx=8)
        self.spark_ram = Sparkline(self.spark_ram_frame, color=T.PURPLE)
        self.spark_ram.pack(fill="x", expand=True, padx=8, pady=4)

        self.bar_frame = ctk.CTkFrame(self.metrics_container, fg_color=T.BG, corner_radius=0)
        self.bar_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        self.bar_frame.grid_columnconfigure(0, weight=1)
        self.bar_frame.grid_rowconfigure(0, weight=1)

        self.inner_bar_frame = T.card(self.bar_frame, corner_radius=T.RADIUS_MD)
        self.inner_bar_frame.grid(row=0, column=0, sticky="nsew")
        self.inner_hub = ctk.CTkFrame(self.inner_bar_frame, fg_color=T.SURFACE, corner_radius=0)
        self.inner_hub.pack(fill="both", expand=True, padx=20, pady=20)

        self.tbar_cpu = TelemetryBar(self.inner_hub, "CPU Freq", T.ACCENT)
        self.tbar_cpu.pack(fill="x", pady=8)
        self.tbar_gpu = TelemetryBar(self.inner_hub, "GPU Pwr", T.GREEN)
        self.tbar_gpu.pack(fill="x", pady=8)
        self.tbar_net = TelemetryBar(self.inner_hub, "Red", T.PURPLE)
        self.tbar_net.pack(fill="x", pady=8)
        self.tbar_disk = TelemetryBar(self.inner_hub, "Disco I/O", T.ORANGE)
        self.tbar_disk.pack(fill="x", pady=8)
        self.tbar_power = TelemetryBar(self.inner_hub, "Consumo", T.AMBER)
        self.tbar_power.pack(fill="x", pady=8)
        self.tbar_temp_cpu = TelemetryBar(self.inner_hub, "Temp CPU", T.RED)
        self.tbar_temp_cpu.pack(fill="x", pady=8)
        self.tbar_temp_gpu = TelemetryBar(self.inner_hub, "Temp GPU", T.RED)
        self.tbar_temp_gpu.pack(fill="x", pady=10)

        self.power_frame = T.card(self.metrics_container, corner_radius=T.RADIUS_MD)
        self.power_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=40, pady=(0, 30))
        self.power_frame.grid_columnconfigure(1, weight=1)
        T.heading(self.power_frame, "Perfil de energía", size=14).grid(row=0, column=0, padx=20, pady=15, sticky="w")

        self.power_plans, active_plan = SystemMetrics.get_power_plans()
        plan_names = list(self.power_plans.keys())

        def plan_score(name):
            n = name.lower()
            if "ximo" in n or "ultimate" in n or "max" in n:
                return 2
            if "alto" in n or "high" in n:
                return 1
            return 0

        plan_names.sort(key=plan_score)
        self.power_buttons_frame = ctk.CTkFrame(self.power_frame, fg_color="#161B22", corner_radius=0)
        self.power_buttons_frame.grid(row=0, column=1, sticky="ew", padx=20, pady=15)
        self.power_btns = {}
        self._plan_score = plan_score
        self._current_power_plan = active_plan
        for plan_name in plan_names:
            icon = "⚡ "
            lower_name = plan_name.lower()
            is_extreme = plan_score(plan_name) == 2
            if "equili" in lower_name:
                icon = "⚖️ "
            elif is_extreme:
                icon = "🔥 "
            elif "alto" in lower_name or "perf" in lower_name:
                icon = "🚀 "
            elif "econ" in lower_name or "ahorr" in lower_name:
                icon = "🌿 "
            btn = ctk.CTkButton(
                self.power_buttons_frame, text=f"{icon}{plan_name}",
                font=T.font(12, "bold"),
                fg_color="transparent",
                text_color=T.TEXT,
                hover_color=T.SURFACE_HOVER,
                border_width=1, border_color=T.BORDER,
                corner_radius=6, height=32,
                command=lambda n=plan_name: self.change_power_plan(n),
            )
            btn.pack(side="left", padx=5)
            self.power_btns[plan_name] = btn
        if active_plan:
            self._highlight_power_plan(active_plan)

        self.after(500, self._sync_power_plans)
        self._after_job = None
        self.update_metrics()

    def apply_theme(self):
        self.configure(fg_color=T.BG)
        self.top_frame.configure(fg_color=T.BG)
        self.specs_frame.configure(fg_color=T.BG)
        self.title_label.configure(text_color=T.TEXT)
        self.uptime_label.configure(text_color=T.TEXT_SEC)
        self.health_frame.configure(fg_color=T.ELEVATED, border_color=T.ACCENT)
        self.health_label.configure(text_color=T.TEXT)
        self.disk_section.configure(fg_color=T.SURFACE, border_color=T.BORDER)
        self.metrics_container.configure(fg_color=T.SURFACE, border_color=T.BORDER)
        self.circle_frame.configure(fg_color=T.BG)
        self.bar_frame.configure(fg_color=T.BG)
        self.inner_bar_frame.configure(fg_color=T.SURFACE, border_color=T.BORDER)
        self.inner_hub.configure(fg_color=T.SURFACE)
        self.power_frame.configure(fg_color=T.SURFACE, border_color=T.BORDER)
        self.spark_cpu_frame.configure(fg_color=T.SURFACE)
        self.spark_ram_frame.configure(fg_color=T.SURFACE)
        for prog, color in (
            (self.cpu_progress, T.ACCENT),
            (self.gpu_progress, T.GREEN),
            (self.ram_progress, T.PURPLE),
            (self.disk_progress, T.ORANGE),
        ):
            prog.bg_color = T.CANVAS_BG
            prog.configure(bg=T.CANVAS_BG)
            prog.text_color = T.TEXT
            prog.color = color
            w, h = prog.winfo_width(), prog.winfo_height()
            if w > 1 and h > 1:
                prog._redraw(w, h)
        self.spark_cpu.color = T.ACCENT
        self.spark_ram.color = T.PURPLE
        self.spark_cpu.configure(bg=T.SURFACE)
        self.spark_ram.configure(bg=T.SURFACE)
        for card in [self.cpu_card, self.gpu_card, self.ram_card] + self.disk_cards:
            card.configure(fg_color=T.SURFACE, border_color=T.BORDER)
            card._default_border = T.BORDER
            card.title_label.configure(text_color=T.TEXT_SEC)
            card.val_label.configure(text_color=T.TEXT)
            card.sub_label.configure(text_color=T.TEXT_SEC)
        for bar, color in (
            (self.tbar_cpu, T.ACCENT),
            (self.tbar_gpu, T.GREEN),
            (self.tbar_net, T.PURPLE),
            (self.tbar_disk, T.ORANGE),
            (self.tbar_power, T.AMBER),
            (self.tbar_temp_cpu, T.RED),
            (self.tbar_temp_gpu, T.RED),
        ):
            bar.bar.configure(progress_color=color, fg_color=T.ELEVATED)
            bar.title_lbl.configure(text_color=T.TEXT_SEC)
            bar.val_lbl.configure(text_color=T.TEXT)
        if getattr(self, "_current_power_plan", None):
            self._highlight_power_plan(self._current_power_plan)

    def on_show(self):
        if not self._after_job:
            self.update_metrics()
        self.update_idletasks()

    def on_hide(self):
        if self._after_job:
            try:
                self.after_cancel(self._after_job)
            except Exception:
                pass
            self._after_job = None

    def _on_metrics_resize(self, event=None):
        w = self.metrics_container.winfo_width()
        should_stack = w < 700
        if should_stack != self._stacked_layout:
            self._stacked_layout = should_stack
            if should_stack:
                self.circle_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
                self.bar_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
            else:
                self.circle_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
                self.bar_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)

    def _sync_power_plans(self):
        try:
            self.power_plans, current_active = SystemMetrics.get_power_plans()
            if current_active:
                self._power_synced = True
                self._highlight_power_plan(current_active)
            elif not self._power_synced:
                self.after(500, self._sync_power_plans)
        except Exception:
            self.after(500, self._sync_power_plans)

    def _highlight_power_plan(self, selection):
        self._current_power_plan = selection
        for name, btn in self.power_btns.items():
            is_extreme = self._plan_score(name) == 2
            active_bg = T.AMBER if is_extreme else T.ACCENT
            hover_bg = T.ORANGE if is_extreme else T.ACCENT_HOVER
            inactive_border = T.AMBER if is_extreme else T.BORDER
            inactive_text = T.AMBER if is_extreme else T.TEXT
            active_text = T.BG
            if name == selection:
                btn.configure(fg_color=active_bg, text_color=active_text, border_color=active_bg, hover_color=hover_bg)
            else:
                btn.configure(fg_color="transparent", text_color=inactive_text, border_color=inactive_border, hover_color=T.SURFACE_HOVER)

    def _get_drive_usage(self):
        self._drive_usage_tick += 1
        if self._drive_usage_tick % 4 == 1 or not self._drive_usage_cache:
            self._drive_usage_cache = SystemMetrics.get_all_drive_usage()
        return self._drive_usage_cache

    def _build_disk_cards(self, disks):
        for card in self.disk_cards:
            card.destroy()
        self.disk_cards = []
        max_cols = 3
        self.disk_cards_frame.grid_columnconfigure(list(range(max_cols)), weight=1)
        drive_usage = self._get_drive_usage()
        letters = sorted(drive_usage.keys())

        for i, disk in enumerate(disks):
            col = i % max_cols
            row = i // max_cols
            label = f"DISCO {i + 1}"
            letter = letters[i] if i < len(letters) else None
            if letter:
                label = f"{letter}"
            pad_x = (0, 5) if col == 0 else (5, 0) if col == max_cols - 1 else 5
            card = SpecCard(self.disk_cards_frame, self.disk_img, label, "...", sub_value=disk["model"], color="#F85149")
            card.grid(row=row, column=col, sticky="ew", padx=pad_x, pady=5)
            card._drive_letter = letter
            self.disk_cards.append(card)
        self._disks_built = True

    def change_power_plan(self, selection):
        self._highlight_power_plan(selection)
        guid = self.power_plans.get(selection)
        SystemMetrics.set_power_plan(guid)

    def _format_gpu_clocks(self, live_data):
        core = live_data.get("gpu_clock_core")
        mem = live_data.get("gpu_clock_mem")
        if core is None and mem is None:
            return "Frecuencia: N/A"
        core_s = f"{core} MHz" if core else "N/A"
        mem_s = f"{mem} MHz" if mem else "N/A"
        return f"Gr: {core_s} | VRAM: {mem_s}"

    def update_metrics(self):
        cpu = SystemMetrics.get_cpu_usage()
        ram_data = SystemMetrics.get_ram_usage()
        disk_data = SystemMetrics.get_disk_usage("C:\\")
        score = SystemMetrics.calculate_health_score()
        hw_specs = SystemMetrics.get_hardware_specs()
        live_data = SystemMetrics.get_dynamic_telemetry()
        _, uptime_str = SystemMetrics.get_uptime_hours()
        self.uptime_label.configure(text=f"Uptime: {uptime_str}")

        cpu_name = hw_specs["CPU"] if len(hw_specs["CPU"]) < 55 else hw_specs["CPU"][:52] + "..."
        gpu_name = hw_specs["GPU"] if len(hw_specs["GPU"]) < 55 else hw_specs["GPU"][:52] + "..."
        ram_type = hw_specs.get("RAM_Type", "RAM")
        if len(ram_type) > 55:
            ram_type = ram_type[:52] + "..."

        self.cpu_card.update_values(f"{live_data['cpu_ghz']} GHz", sub_value=cpu_name)
        self.gpu_card.update_values(self._format_gpu_clocks(live_data), sub_value=gpu_name, title="TARJETA GRÁFICA")
        self.ram_card.update_values(f"{ram_data['used_gb']} GB / {hw_specs['RAM_GB']} GB", sub_value=ram_type)

        disks = hw_specs.get("Disks", [])
        if disks and not self._disks_built:
            self._build_disk_cards(disks)

        drive_usage = self._get_drive_usage()
        letters = sorted(drive_usage.keys())
        for i, card in enumerate(self.disk_cards):
            if i < len(disks):
                d = disks[i]
                model_short = d["model"] if len(d["model"]) < 38 else d["model"][:35] + "..."
                letter = getattr(card, "_drive_letter", None) or (letters[i] if i < len(letters) else None)
                if letter and letter in drive_usage:
                    du = drive_usage[letter]
                    val = f"{du['used_gb']} GB / {du['total_gb']} GB"
                elif i == 0:
                    val = f"{disk_data['total_gb'] - disk_data['free_gb']:.1f} GB / {disk_data['total_gb']} GB"
                else:
                    val = f"{d['gb']} GB"
                card.update_values(val, sub_value=model_short)

        self.cpu_progress.draw_arc(cpu)
        self.gpu_progress.title = gpu_name[:20]
        self.gpu_progress.draw_arc(live_data["gpu_percent"])
        self.ram_progress.draw_arc(ram_data["percent"])
        self.disk_progress.draw_arc(disk_data["percent"])

        self.spark_cpu.push(cpu)
        self.spark_ram.push(ram_data["percent"])

        status_text = "Óptimo" if score >= 85 else "Estable" if score >= 60 else "Atención"
        color = T.GREEN if score >= 85 else T.AMBER if score >= 60 else T.RED
        self.health_frame.configure(border_color=color)
        self.health_label.configure(text=f"Score: {score}/100 - {status_text}", text_color=color)

        cpu_pct = min(1.0, live_data["cpu_ghz"] / 6.0)
        net_total = live_data["net_dl_mbs"] + live_data["net_ul_mbs"]
        net_pct = min(1.0, net_total / 100.0)
        disk_total = live_data["disk_read_mbs"] + live_data["disk_write_mbs"]
        disk_pct = min(1.0, disk_total / 500.0)
        gpu_pct = min(1.0, live_data["gpu_power_w"] / 400.0)
        pwr_pct = min(1.0, live_data["total_power_w"] / 800.0)
        temp_gpu_pct = min(1.0, live_data["gpu_temp_c"] / 100.0)
        temp_cpu_pct = min(1.0, live_data["cpu_temp_c"] / 100.0)

        self.tbar_cpu.update_bar(cpu_pct, f"{live_data['cpu_ghz']} GHz")
        self.tbar_gpu.update_bar(gpu_pct, f"{live_data['gpu_power_w']} W ({live_data['gpu_percent']}%)")
        self.tbar_net.update_bar(net_pct, f"↓ {live_data['net_dl_mbs']} ↑ {live_data['net_ul_mbs']}")
        self.tbar_disk.update_bar(disk_pct, f"R {live_data['disk_read_mbs']} W {live_data['disk_write_mbs']}")
        self.tbar_power.update_bar(pwr_pct, f"~ {live_data['total_power_w']} W")
        self.tbar_temp_cpu.update_bar(temp_cpu_pct, f"{live_data['cpu_temp_c']} °C")
        gpu_temp = live_data["gpu_temp_c"] if live_data["gpu_temp_c"] > 0 else "N/A"
        self.tbar_temp_gpu.update_bar(temp_gpu_pct if live_data["gpu_temp_c"] > 0 else 0, f"{gpu_temp} °C" if gpu_temp != "N/A" else "N/A")

        if self._power_synced:
            try:
                _, current_active = SystemMetrics.get_power_plans()
                if current_active:
                    self._highlight_power_plan(current_active)
            except Exception:
                pass

        if self.winfo_exists():
            self._after_job = self.after(2000, self.update_metrics)
