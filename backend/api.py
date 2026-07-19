"""Puente Python <-> JavaScript para la UI web (pywebview).

Las operaciones largas corren en hilos propios del backend; la UI hace
polling de los objetos de trabajo (job) para pintar progreso.
"""
from __future__ import annotations

import base64
import json
import os
import threading

import requests as _requests

from backend.mas_activation import MasActivation
from backend.optimization_engine import OptimizationEngine, TWEAK_META, TWEAK_ORDER, REVERTABLE
from backend.system_metrics import SystemMetrics
from backend.update_manager import UpdateManager
from backend.utils import get_base_path, get_data_path, request_admin_restart
from backend.winget_manager import WingetManager
from version import __version__

TWEAK_DESC = {
    "restore_point": "Crea un punto de restauración antes de aplicar cambios.",
    "telemetry": "Desactiva servicios y tareas de telemetría de Windows.",
    "telemetry_extra": "Desactiva servicios de telemetría adicionales.",
    "power_plan": "Activa el plan de energía Ultimate Performance.",
    "power_fine": "Ajustes finos de energía para máximo rendimiento.",
    "temp": "Limpieza profunda de archivos temporales.",
    "visual_effects": "Ajusta efectos visuales para rendimiento.",
    "disk_optimize": "Optimiza y desfragmenta las unidades.",
    "standby_ram": "Libera la RAM en caché standby.",
    "gaming": "Desactiva GameDVR y optimiza para juegos.",
    "game_mode": "Activa el Game Mode de Windows.",
    "hags": "Programación de GPU acelerada por hardware.",
    "mmcss": "Prioriza juegos en el programador multimedia.",
    "mouse_precision": "Desactiva aceleración del ratón (1:1).",
    "vbs": "Desactiva VBS/HVCI (seguridad basada en virtualización).",
    "core_parking": "Evita que Windows aparque núcleos de CPU.",
    "windowed_opt": "Optimizaciones para juegos en ventana.",
    "auto_maintenance": "Desactiva el mantenimiento automático.",
    "power_throttling": "Desactiva el power throttling.",
    "delivery_opt": "Desactiva la optimización de entrega (P2P updates).",
    "network": "Vacía DNS y reinicia Winsock.",
    "dns_custom": "Configura DNS rápidos (Google/Cloudflare).",
    "services": "Desactiva SysMain y Windows Search.",
    "startup": "Desactiva programas de inicio de terceros.",
    "fast_startup": "Acelera el arranque del sistema.",
    "tips_suggestions": "Desactiva tips y sugerencias de Windows.",
    "hibernate_off": "Desactiva la hibernación (libera espacio).",
    "ntfs_optimize": "NTFS sin registro de último acceso.",
    "background_apps": "Desactiva apps en segundo plano.",
    "widgets_off": "Desactiva los widgets de Windows.",
    "fullscreen_opt": "Desactiva optimizaciones de pantalla completa.",
    "tcp_optimize": "TCP de baja latencia para juegos online.",
}


def _icon_data_uri(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except Exception:
        return None


class Api:
    def __init__(self):
        self._window = None
        self._wm = WingetManager()
        self._updater = UpdateManager()
        self._bundled_icons = os.path.join(get_base_path(), "assets", "icons")
        self._cache_icons = os.path.join(get_data_path(), "icons")
        os.makedirs(self._cache_icons, exist_ok=True)
        self._icon_downloads: set[str] = set()

        with open(os.path.join(get_base_path(), "data", "apps_database.json"), "r", encoding="utf-8") as f:
            self._db = json.load(f)
        self._app_lookup = self._build_app_lookup()

        self._tweak_job = self._idle_job()
        self._install_job = self._idle_job()
        self._mas = MasActivation()

        self._engine = OptimizationEngine(
            callback_log=self._on_engine_log,
            on_progress=self._on_engine_progress,
            on_tweak_status=self._on_engine_status,
            on_done=self._on_engine_done,
        )

    # ---------- infra ----------

    @staticmethod
    def _idle_job() -> dict:
        return {
            "running": False, "done": False, "current": 0, "total": 0,
            "label": "", "logs": [], "results": [], "statuses": {},
        }

    def set_window(self, window):
        self._window = window

    def _build_app_lookup(self) -> dict:
        lookup = {}
        for cat in self._db.get("categorias", []):
            for app in cat.get("apps", []):
                lookup[app["id"]] = {
                    "nombre": app["nombre"],
                    "categoria": cat["nombre"],
                    "winget_id": app.get("winget_id", app["id"]),
                    "source": app.get("source"),
                    "install_silent": app.get("install_silent", True),
                    "install_dependencies": app.get("install_dependencies", True),
                    "hub_unavailable": app.get("hub_unavailable", False),
                    "install_mode": app.get("install_mode", "winget"),
                    "download_url": app.get("download_url"),
                    "download_page": app.get("download_page"),
                    "office_product": app.get("office_product"),
                    "dominio": app.get("dominio"),
                }
        return lookup

    def _app_specs(self, app_ids: list[str]) -> list[dict]:
        specs = []
        for aid in app_ids:
            meta = self._app_lookup.get(aid, {})
            if meta.get("hub_unavailable") and meta.get("install_mode") not in ("direct", "office_c2r"):
                continue
            specs.append({
                "catalog_id": aid,
                "winget_id": meta.get("winget_id", aid),
                "name": meta.get("nombre", aid),
                "source": meta.get("source"),
                "install_silent": meta.get("install_silent", True),
                "install_dependencies": meta.get("install_dependencies", True),
                "install_mode": meta.get("install_mode", "winget"),
                "download_url": meta.get("download_url"),
                "download_page": meta.get("download_page"),
                "office_product": meta.get("office_product"),
            })
        return specs

    def get_catalog_health(self):
        """Estado winget de cada app del catálogo."""
        items = []
        for aid, meta in self._app_lookup.items():
            if meta.get("hub_unavailable"):
                items.append({"id": aid, "nombre": meta["nombre"], "status": "unavailable", "reason": "No disponible en winget"})
                continue
            wid = meta.get("winget_id", aid)
            chk = self._wm.check_package_available(wid)
            items.append({
                "id": aid,
                "nombre": meta["nombre"],
                "status": "ok" if chk.get("available") else "broken",
                "reason": chk.get("reason", ""),
                "source": chk.get("source", ""),
            })
        ok = sum(1 for i in items if i["status"] == "ok")
        return {"items": items, "ok": ok, "total": len(items)}

    def get_app_catalog(self):
        return {"apps": self._app_lookup}

    def get_version(self):
        return {"version": __version__}

    # ---------- dashboard ----------

    def get_metrics(self):
        try:
            cpu = SystemMetrics.get_cpu_usage()
            ram = SystemMetrics.get_ram_usage()
            disk = SystemMetrics.get_disk_usage("C:\\")
            live = SystemMetrics.get_dynamic_telemetry()
            uptime_h, uptime_str = SystemMetrics.get_uptime_hours()

            score = 100
            if cpu > 80:
                score -= 15
            elif cpu > 50:
                score -= 5
            if ram["percent"] > 90:
                score -= 20
            elif ram["percent"] > 70:
                score -= 10
            if disk["percent"] > 90:
                score -= 15
            elif disk["percent"] > 80:
                score -= 5
            temp = live.get("cpu_temp_c", 0)
            if temp > 85:
                score -= 15
            elif temp > 75:
                score -= 8
            elif temp > 65:
                score -= 3
            if uptime_h > 168:
                score -= 10
            elif uptime_h > 72:
                score -= 5
            score = max(0, min(100, score))

            return {
                "ok": True,
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "live": live,
                "uptime": uptime_str,
                "score": score,
                "drives": SystemMetrics.get_all_drive_usage(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_specs(self):
        try:
            specs = SystemMetrics.get_hardware_specs()
            return {"ok": True, "specs": specs}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_power_plans(self):
        try:
            plans, active = SystemMetrics.get_power_plans()
            return {"ok": True, "plans": list(plans.keys()), "active": active}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_power_plan(self, name):
        try:
            plans, _ = SystemMetrics.get_power_plans()
            guid = plans.get(name)
            if guid:
                SystemMetrics.set_power_plan(guid)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- optimizador ----------

    def is_admin(self):
        return {"admin": OptimizationEngine.is_admin()}

    def restart_admin(self):
        def worker():
            try:
                request_admin_restart()
            except SystemExit:
                # Elevación lanzada correctamente: cerrar esta instancia
                if self._window:
                    try:
                        self._window.destroy()
                    except Exception:
                        pass
                os._exit(0)

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    def get_tweaks(self):
        applied = set(self._engine.get_applied_tweaks())
        tweaks = []
        for tid in TWEAK_ORDER:
            meta = TWEAK_META[tid]
            tweaks.append({
                "id": tid,
                "label": meta["label"],
                "desc": TWEAK_DESC.get(tid, ""),
                "admin": meta.get("admin", False),
                "revertable": meta.get("revertable", False),
                "applied": tid in applied,
            })
        return {"tweaks": tweaks, "isAdmin": OptimizationEngine.is_admin()}

    def _on_engine_log(self, msg):
        self._tweak_job["logs"].append(msg)

    def _on_engine_progress(self, done, total, tweak_id, label):
        self._tweak_job.update({"current": done, "total": total, "label": label or ""})

    def _on_engine_status(self, tweak_id, status):
        self._tweak_job["statuses"][tweak_id] = status

    def _on_engine_done(self, results):
        self._tweak_job["results"] = [
            {"id": r.tweak_id, "status": r.status, "message": r.message} for r in results
        ]
        self._tweak_job["running"] = False
        self._tweak_job["done"] = True

    def start_tweaks(self, tweak_ids):
        if self._tweak_job["running"]:
            return {"ok": False, "error": "Ya hay una operación en curso"}
        self._tweak_job = self._idle_job()
        self._tweak_job["running"] = True
        self._engine.optimize_all({tid: True for tid in tweak_ids})
        return {"ok": True}

    def start_revert(self, tweak_ids):
        if self._tweak_job["running"]:
            return {"ok": False, "error": "Ya hay una operación en curso"}
        self._tweak_job = self._idle_job()
        self._tweak_job["running"] = True
        self._engine.revert_tweaks([t for t in tweak_ids if t in REVERTABLE])
        return {"ok": True}

    def get_tweak_job(self):
        return self._tweak_job

    # ---------- software hub ----------

    def get_categories(self):
        cats = []
        for cat in self._db.get("categorias", []):
            ids = [a["id"] for a in cat["apps"]]
            cats.append({
                "id": cat["id"],
                "nombre": cat["nombre"],
                "count": len(ids),
                "updates": self._wm.count_updates_in_apps(ids),
            })
        return {"categories": cats, "wingetAvailable": self._wm.is_available}

    def _find_icon(self, app_id: str) -> str | None:
        for base in (self._cache_icons, self._bundled_icons):
            p = os.path.join(base, f"{app_id}.png")
            if os.path.exists(p):
                return p
        return None

    def _download_icon_async(self, app_id: str, domain: str):
        if app_id in self._icon_downloads:
            return
        self._icon_downloads.add(app_id)

        def worker():
            try:
                url = f"https://icons.duckduckgo.com/ip3/{domain}.ico"
                resp = _requests.get(url, timeout=6)
                if resp.status_code == 200 and len(resp.content) > 100:
                    with open(os.path.join(self._cache_icons, f"{app_id}.png"), "wb") as f:
                        f.write(resp.content)
            except Exception:
                pass
            finally:
                self._icon_downloads.discard(app_id)

        threading.Thread(target=worker, daemon=True).start()

    def get_apps(self, category_id):
        cat = next((c for c in self._db.get("categorias", []) if c["id"] == category_id), None)
        if not cat:
            return {"apps": []}
        apps = []
        for a in cat["apps"]:
            icon_path = self._find_icon(a["id"])
            if not icon_path and a.get("dominio"):
                self._download_icon_async(a["id"], a["dominio"])
            apps.append({
                "id": a["id"],
                "nombre": a["nombre"],
                "desc": a["desc"],
                "size": a.get("size", ""),
                "rating": a.get("rating", ""),
                "icon": _icon_data_uri(icon_path) if icon_path else None,
                "unavailable": bool(a.get("hub_unavailable")),
                "install_mode": a.get("install_mode", "winget"),
                "download_url": a.get("download_url"),
                "download_page": a.get("download_page") or (
                    f"https://{a['dominio']}" if a.get("dominio") else None
                ),
            })
        return {"apps": apps, "loaded": self._wm.is_loaded}

    def get_app_statuses(self, app_ids):
        out = {}
        for app_id in app_ids:
            meta = self._app_lookup.get(app_id, {})
            wid = meta.get("winget_id", app_id)
            info = self._wm.get_app_info(wid)
            if info.get("status") == "not_installed":
                info = self._wm.get_app_info(app_id)
            status = info.get("status")
            out[app_id] = {
                "installed": status == "installed",
                "update_available": status == "installed" and bool(info.get("available")),
                "version": info.get("version", ""),
                "available_version": info.get("available", ""),
            }
        return {"statuses": out, "loaded": self._wm.is_loaded}

    def get_outdated_count(self):
        return self.get_outdated_apps()

    def get_outdated_apps(self):
        apps = []
        if not self._wm.is_loaded:
            return {"apps": [], "count": 0, "loaded": False}
        for aid, meta in self._app_lookup.items():
            if meta.get("hub_unavailable") and meta.get("install_mode") not in ("direct", "office_c2r"):
                continue
            if meta.get("install_mode") in ("direct", "office_c2r"):
                continue
            wid = meta.get("winget_id", aid)
            if self._wm.is_outdated(wid) or self._wm.is_outdated(aid):
                apps.append({"id": aid, "nombre": meta["nombre"]})
        return {"apps": apps, "count": len(apps), "loaded": True}

    def _make_install_callbacks(self):
        job = self._install_job

        def on_progress(current, total, app_id):
            job.update({"current": current, "total": total, "label": app_id or ""})

        def on_log(line):
            clean = line.strip()
            if clean and "\u2588" not in clean and "\u2591" not in clean:
                job["logs"].append(clean)
                if len(job["logs"]) > 400:
                    del job["logs"][:100]

        def on_done(results):
            job["results"] = results
            job["running"] = False
            job["done"] = True

        return on_progress, on_log, on_done

    def start_install(self, app_ids):
        if self._install_job["running"]:
            return {"ok": False, "error": "Ya hay una instalación en curso"}
        specs = self._app_specs(app_ids)
        if not specs:
            return {"ok": False, "error": "Ninguna app seleccionada está disponible en winget"}
        self._install_job = self._idle_job()
        self._install_job["running"] = True
        self._install_job["total"] = len(specs)
        on_progress, on_log, on_done = self._make_install_callbacks()
        self._wm.install_apps(specs, on_progress=on_progress, on_log=on_log, on_done=on_done)
        return {"ok": True}

    def start_upgrade(self, app_ids):
        if self._install_job["running"]:
            return {"ok": False, "error": "Ya hay una instalación en curso"}
        self._install_job = self._idle_job()
        self._install_job["running"] = True
        self._install_job["total"] = len(app_ids)
        on_progress, on_log, on_done = self._make_install_callbacks()
        self._wm.upgrade_apps(self._app_specs(app_ids), on_progress=on_progress, on_log=on_log, on_done=on_done)
        return {"ok": True}

    def open_app_download(self, app_id: str):
        """Abre enlace de descarga en el navegador predeterminado."""
        meta = self._app_lookup.get(app_id)
        if not meta:
            return {"ok": False, "error": "App no encontrada"}
        url = meta.get("download_page") or meta.get("download_url")
        if not url and meta.get("dominio"):
            url = f"https://{meta['dominio']}"
        if not url:
            return {"ok": False, "error": "Sin enlace de descarga configurado"}
        try:
            import webbrowser
            webbrowser.open(url)
            return {"ok": True, "url": url}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def start_uninstall(self, app_id):
        if self._install_job["running"]:
            return {"ok": False, "error": "Ya hay una operación en curso"}
        meta = self._app_lookup.get(app_id, {})
        winget_id = meta.get("winget_id", app_id)
        display_name = meta.get("nombre", app_id)
        self._install_job = self._idle_job()
        self._install_job["running"] = True
        self._install_job["total"] = 1
        self._install_job["label"] = display_name
        job = self._install_job

        def on_log(line):
            clean = line.strip()
            if clean:
                job["logs"].append(clean)

        def on_done(result):
            result["id"] = app_id
            job["results"] = [result]
            job["running"] = False
            job["done"] = True

        self._wm.uninstall_app(winget_id, display_name=display_name, on_log=on_log, on_done=on_done)
        return {"ok": True}

    def get_install_job(self):
        return self._install_job

    def cancel_install(self):
        self._wm.cancel_active()
        return {"ok": True}

    # ---------- updates ----------

    def check_update(self):
        result = {}
        event = threading.Event()

        def cb(info):
            result["info"] = info
            event.set()

        self._updater.check_for_update(cb)
        event.wait(timeout=15)
        info = result.get("info")
        if info:
            info["available"] = True
        return {"update": info}

    def start_app_update(self, url):
        def worker():
            self._updater.download_and_install(url)

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}

    # ---------- massgrave / MAS ----------

    def get_mas_info(self):
        return self._mas.get_info()

    def get_mas_status(self):
        return self._mas.get_activation_status()

    def launch_mas(self, method="online"):
        return self._mas.launch(method)

    def auto_activate_mas(self, use_doh=False):
        return self._mas.auto_activate(use_doh=use_doh)

    def get_mas_job(self):
        return self._mas.get_job()
