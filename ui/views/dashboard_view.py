"""Glassmorphism dashboard with live system metrics and copy support."""
import customtkinter as ctk
import threading
from backend.system_metrics import SystemMetrics
from backend.utils import get_base_path
from ui import theme as T
from ui.widgets import CircularGauge, Sparkline, TelemetryBar, SpecCard
from PIL import Image
import os


def fmt_gb(v):
    if v < 1:
        return f"{int(v * 1024)} MB"
    return f"{v:.1f} GB"


class DashboardView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=T.BG_PRIMARY, corner_radius=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._disks_built = False
        self._power_synced = False
        self._stacked = False
        self._drive_cache = {}
        self._drive_tick = 0
        self._job = None
        self._busy = False
        self._tick = 0
        self._hidden = False

        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 8))
        top.grid_columnconfigure(1, weight=1)

        self._title = T.heading(top, "Dashboard", size=30)
        self._title.grid(row=0, column=0, sticky="w")

        self._uptime = ctk.CTkLabel(top, text="Uptime: \u2014", font=T.font(12, mono=True), text_color=T.TEXT_SEC)
        self._uptime.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self._health_frame = T.glass_card(top, fg_color=T.SURFACE, border_color=T.ACCENT)
        self._health_frame.grid(row=0, column=2, rowspan=2, sticky="e")
        self._health_lbl = ctk.CTkLabel(self._health_frame, text="Evaluando sistema\u2026", font=T.font(15, "bold"))
        self._health_lbl.pack(padx=20, pady=8)

        # Specs row
        self._specs_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._specs_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        self._specs_frame.grid_columnconfigure((0, 1, 2), weight=1)

        base = get_base_path()
        _load = lambda p: ctk.CTkImage(
            light_image=Image.open(os.path.join(base, "assets", "icons", p)),
            dark_image=Image.open(os.path.join(base, "assets", "icons", p)),
            size=(36, 36),
        )
        self._cpu_img = _load("cpu.png")
        self._gpu_img = _load("gpu.png")
        self._ram_img = _load("ram.png")
        self._disk_img = _load("disk.png")

        self._cpu_card = SpecCard(self._specs_frame, self._cpu_img, "PROCESADOR", "Cargando\u2026", "\u2026", T.ACCENT)
        self._cpu_card.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._gpu_card = SpecCard(self._specs_frame, self._gpu_img, "GR\u00c1FICA", "Cargando\u2026", "\u2026", T.GREEN)
        self._gpu_card.grid(row=0, column=1, sticky="ew", padx=5)
        self._ram_card = SpecCard(self._specs_frame, self._ram_img, "MEMORIA RAM", "Cargando\u2026", "\u2026", T.PURPLE)
        self._ram_card.grid(row=0, column=2, sticky="ew", padx=(5, 0))

        # Disk section
        self._disk_sec = T.glass_card(self)
        self._disk_sec.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))
        self._disk_sec.grid_columnconfigure(0, weight=1)
        dh = ctk.CTkFrame(self._disk_sec, fg_color="transparent")
        dh.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 4))
        T.section_label(dh, "ALMACENAMIENTO").pack(side="left")
        self._disk_cf = ctk.CTkFrame(self._disk_sec, fg_color="transparent")
        self._disk_cf.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self._disk_cards = []

        # Metrics container
        self._mc = T.glass_panel(self)
        self._mc.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 16))
        self._mc.grid_rowconfigure(0, weight=1)
        self._mc.grid_rowconfigure(1, weight=0)
        self._mc.grid_columnconfigure(0, weight=3)
        self._mc.grid_columnconfigure(1, weight=2)
        self._mc.bind("<Configure>", self._on_resize)

        # Gauges
        self._gf = ctk.CTkFrame(self._mc, fg_color="transparent")
        self._gf.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        self._gf.grid_columnconfigure((0, 1), weight=1)
        self._gf.grid_rowconfigure((0, 1, 2, 3), weight=1)

        self._cpu_g = CircularGauge(self._gf, T.ACCENT, "CPU")
        self._cpu_g.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self._gpu_g = CircularGauge(self._gf, T.GREEN, "GPU")
        self._gpu_g.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self._ram_g = CircularGauge(self._gf, T.PURPLE, "RAM")
        self._ram_g.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self._disk_g = CircularGauge(self._gf, T.ORANGE, "Disco")
        self._disk_g.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

        # Sparklines
        sc = ctk.CTkFrame(self._gf, fg_color=T.SURFACE, corner_radius=T.RADIUS_SM, height=36)
        sc.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        T.section_label(sc, "CPU 60s").pack(side="left", padx=8)
        self._sp_cpu = Sparkline(sc, T.ACCENT)
        self._sp_cpu.pack(fill="x", expand=True, padx=8, pady=4)

        sr = ctk.CTkFrame(self._gf, fg_color=T.SURFACE, corner_radius=T.RADIUS_SM, height=36)
        sr.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))
        T.section_label(sr, "RAM 60s").pack(side="left", padx=8)
        self._sp_ram = Sparkline(sr, T.PURPLE)
        self._sp_ram.pack(fill="x", expand=True, padx=8, pady=4)

        # Bars
        self._bf = ctk.CTkFrame(self._mc, fg_color="transparent")
        self._bf.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        self._bf.grid_columnconfigure(0, weight=1)
        self._bf.grid_rowconfigure(0, weight=1)

        ib = T.glass_card(self._bf)
        ib.grid(row=0, column=0, sticky="nsew")
        h = ctk.CTkFrame(ib, fg_color="transparent")
        h.pack(fill="both", expand=True, padx=20, pady=20)

        self._tb = {}
        for key, label, color in [
            ("cpu", "CPU Freq", T.ACCENT), ("gpu", "GPU Pwr", T.GREEN),
            ("net", "Red", T.PURPLE), ("dio", "Disco I/O", T.ORANGE),
            ("pwr", "Consumo", T.AMBER), ("tc", "Temp CPU", T.RED),
            ("tg", "Temp GPU", T.RED),
        ]:
            tb = TelemetryBar(h, label, color)
            tb.pack(fill="x", pady=6)
            self._tb[key] = tb

        # Power plans
        self._pf = T.glass_card(self._mc)
        self._pf.grid(row=1, column=0, columnspan=2, sticky="ew", padx=40, pady=(0, 24))
        self._pf.grid_columnconfigure(1, weight=1)
        T.heading(self._pf, "Perfil de energ\u00eda", size=14).grid(row=0, column=0, padx=20, pady=15, sticky="w")

        plans, active = SystemMetrics.get_power_plans()
        names = sorted(plans.keys(), key=lambda n: (
            2 if any(x in n.lower() for x in ["ximo", "ultimate", "max"])
            else 1 if any(x in n.lower() for x in ["alto", "high", "perf"])
            else 0
        ))
        self._pbf = ctk.CTkFrame(self._pf, fg_color=T.BG_SECONDARY)
        self._pbf.grid(row=0, column=1, sticky="ew", padx=20, pady=15)
        self._pbs = {}
        self._cur_plan = active
        for name in names:
            lower = name.lower()
            if "equili" in lower:
                icon = "\u2696 "
            elif any(x in lower for x in ["ximo", "ultimate", "max"]):
                icon = "\U0001f525 "
            elif "alto" in lower or "perf" in lower:
                icon = "\U0001f680 "
            elif "econ" in lower or "ahorr" in lower:
                icon = "\U0001f33f "
            else:
                icon = "\u26a1 "
            btn = ctk.CTkButton(
                self._pbf, text=f"{icon}{name}", font=T.font(12, "bold"),
                fg_color="transparent", text_color=T.TEXT,
                hover_color=T.SURFACE_HOVER, border_width=1, border_color=T.BORDER,
                corner_radius=6, height=32,
                command=lambda n=name: self._change_plan(n),
            )
            btn.pack(side="left", padx=5)
            self._pbs[name] = btn
        if active:
            self._hl_plan(active)
        self.after(500, self._sync_plans)

    def on_show(self):
        self._hidden = False
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.update_metrics()

    def on_hide(self):
        self._hidden = True
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _on_resize(self, _=None):
        if self._hidden:
            return
        w = self._mc.winfo_width()
        s = w < 700
        if s != self._stacked:
            self._stacked = s
            if s:
                self._gf.grid(row=0, column=0, columnspan=2, sticky="nsew")
                self._bf.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
            else:
                self._gf.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
                self._bf.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)

    def _sync_plans(self):
        try:
            _, cur = SystemMetrics.get_power_plans()
            if cur:
                self._power_synced = True
                self._hl_plan(cur)
            elif not self._power_synced:
                self.after(500, self._sync_plans)
        except Exception:
            self.after(500, self._sync_plans)

    def _hl_plan(self, sel):
        self._cur_plan = sel
        for name, btn in self._pbs.items():
            ext = any(x in name.lower() for x in ["ximo", "ultimate", "max"])
            if name == sel:
                btn.configure(
                    fg_color=T.AMBER if ext else T.ACCENT,
                    text_color=T.BG_PRIMARY,
                    border_color=T.AMBER if ext else T.ACCENT,
                    hover_color=T.ORANGE if ext else T.ACCENT_HOVER,
                )
            else:
                btn.configure(
                    fg_color="transparent", text_color=T.AMBER if ext else T.TEXT,
                    border_color=T.AMBER if ext else T.BORDER,
                    hover_color=T.SURFACE_HOVER,
                )

    def _change_plan(self, sel):
        self._hl_plan(sel)
        plans, _ = SystemMetrics.get_power_plans()
        g = plans.get(sel)
        if g:
            SystemMetrics.set_power_plan(g)

    def _drive_usage(self):
        self._drive_tick += 1
        if self._drive_tick % 4 == 1 or not self._drive_cache:
            self._drive_cache = SystemMetrics.get_all_drive_usage()
        return self._drive_cache

    def _build_disks(self, disks):
        for c in self._disk_cards:
            c.destroy()
        self._disk_cards.clear()
        cols = 3
        self._disk_cf.grid_columnconfigure(list(range(cols)), weight=1)
        du = self._drive_usage()
        letters = sorted(du.keys())
        for i, d in enumerate(disks):
            col = i % cols
            row = i // cols
            letter = letters[i] if i < len(letters) else None
            px = (0, 5) if col == 0 else (5, 0) if col == cols - 1 else 5
            card = SpecCard(self._disk_cf, self._disk_img, letter or f"DISCO {i+1}", "...", d["model"][:38], "#F85149")
            card.grid(row=row, column=col, sticky="ew", padx=px, pady=5)
            card._dr_letter = letter
            self._disk_cards.append(card)
        self._disks_built = True

    def _fmt_gpu(self, live):
        c = live.get("gpu_clock_core")
        m = live.get("gpu_clock_mem")
        if c is None and m is None:
            return "Frecuencia: N/A"
        return f"Gr: {c or 'N/A'} MHz | VRAM: {m or 'N/A'} MHz"

    def _health(self, cpu, ram_pct, disk_pct, live, uptime_h):
        s = 100
        if cpu > 80:
            s -= 15
        elif cpu > 50:
            s -= 5
        if ram_pct > 90:
            s -= 20
        elif ram_pct > 70:
            s -= 10
        if disk_pct > 90:
            s -= 15
        elif disk_pct > 80:
            s -= 5
        t = live.get("cpu_temp_c", 0)
        if t > 85:
            s -= 15
        elif t > 75:
            s -= 8
        if uptime_h > 168:
            s -= 5
        return max(0, min(100, s))

    def _snapshot(self):
        cpu = SystemMetrics.get_cpu_usage()
        ram = SystemMetrics.get_ram_usage()
        disk = SystemMetrics.get_disk_usage("C:\\")
        hw = SystemMetrics.get_hardware_specs()
        live = SystemMetrics.get_dynamic_telemetry()
        uh, us = SystemMetrics.get_uptime_hours()
        sc = self._health(cpu, ram["percent"], disk["percent"], live, uh)
        return {"cpu": cpu, "ram": ram, "disk": disk, "sc": sc, "hw": hw, "live": live, "us": us, "uh": uh}

    def update_metrics(self):
        if self._busy:
            return
        self._busy = True

        def _w():
            try:
                s = self._snapshot()
                self.after(0, self._apply, s)
            except Exception:
                self.after(0, self._done)

        threading.Thread(target=_w, daemon=True).start()

    def _done(self):
        self._busy = False
        if not self._hidden and self.winfo_exists():
            self._job = self.after(2000, self.update_metrics)

    def _apply(self, snap):
        try:
            cpu = snap["cpu"]
            ram = snap["ram"]
            disk = snap["disk"]
            sc = snap["sc"]
            hw = snap["hw"]
            live = snap["live"]
            us = snap["us"]
            if self._hidden:
                return
            self._tick += 1

            self._uptime.configure(text=f"Uptime: {us}")

            cn = hw["CPU"][:52] + "..." if len(hw["CPU"]) > 55 else hw["CPU"]
            gn = hw["GPU"][:52] + "..." if len(hw["GPU"]) > 55 else hw["GPU"]
            rt = (hw.get("RAM_Type", "RAM")[:52] + "...") if len(hw.get("RAM_Type", "RAM")) > 55 else hw.get("RAM_Type", "RAM")

            self._cpu_card.update_values(f"{live['cpu_ghz']} GHz", cn)
            self._gpu_card.update_values(self._fmt_gpu(live), gn, "TARJETA GR\u00c1FICA")
            self._ram_card.update_values(f"{fmt_gb(ram['used_gb'])} / {hw['RAM_GB']} GB", rt)

            disks = hw.get("Disks", [])
            if disks and not self._disks_built:
                self._build_disks(disks)

            du = self._drive_usage()
            letters = sorted(du.keys())
            for i, card in enumerate(self._disk_cards):
                if i < len(disks):
                    d = disks[i]
                    letter = getattr(card, "_dr_letter", None) or (letters[i] if i < len(letters) else None)
                    if letter and letter in du:
                        v = f"{fmt_gb(du[letter]['used_gb'])} / {du[letter]['total_gb']} GB"
                    elif i == 0:
                        used = disk["total_gb"] - disk["free_gb"]
                        v = f"{fmt_gb(used)} / {disk['total_gb']} GB"
                    else:
                        v = f"{d['gb']} GB"
                    card.update_values(v, d["model"][:35] + "..." if len(d["model"]) > 38 else d["model"])

            self._cpu_g.draw_arc(cpu)
            self._gpu_g.draw_arc(live["gpu_percent"])
            self._ram_g.draw_arc(ram["percent"])
            self._disk_g.draw_arc(disk["percent"])

            self._sp_cpu.push(cpu)
            self._sp_ram.push(ram["percent"])

            st = "\u00d3ptimo" if sc >= 85 else "Estable" if sc >= 60 else "Atenci\u00f3n"
            co = T.GREEN if sc >= 85 else T.AMBER if sc >= 60 else T.RED
            self._health_frame.configure(border_color=co)
            self._health_lbl.configure(text=f"Score: {sc}/100 \u2014 {st}", text_color=co)

            cpu_pct = min(1.0, live["cpu_ghz"] / 6.0)
            nt = live["net_dl_mbs"] + live["net_ul_mbs"]
            gp_pct = min(1.0, live["gpu_power_w"] / 400.0)
            dt = live["disk_read_mbs"] + live["disk_write_mbs"]

            self._tb["cpu"].update_bar(cpu_pct, f"{live['cpu_ghz']} GHz")
            self._tb["gpu"].update_bar(gp_pct, f"{live['gpu_power_w']} W ({live['gpu_percent']}%)")
            self._tb["net"].update_bar(min(1.0, nt / 100.0), f"\u2193 {live['net_dl_mbs']} \u2191 {live['net_ul_mbs']}")
            self._tb["dio"].update_bar(min(1.0, dt / 500.0), f"R {live['disk_read_mbs']} W {live['disk_write_mbs']}")
            self._tb["pwr"].update_bar(min(1.0, live['total_power_w'] / 800.0), f"~ {live['total_power_w']} W")
            self._tb["tc"].update_bar(min(1.0, live['cpu_temp_c'] / 100.0), f"{live['cpu_temp_c']} \u00b0C")
            gt = live["gpu_temp_c"] if live["gpu_temp_c"] > 0 else "N/A"
            self._tb["tg"].update_bar(
                min(1.0, live["gpu_temp_c"] / 100.0) if live["gpu_temp_c"] > 0 else 0,
                f"{gt} \u00b0C" if gt != "N/A" else "N/A",
            )

            if self._power_synced and self._tick % 15 == 0:
                try:
                    _, cur = SystemMetrics.get_power_plans()
                    if cur:
                        self._hl_plan(cur)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self._done()
