import subprocess
import threading
import re

class WingetManager:
    def __init__(self):
        self.installed_apps = {}
        self.is_loaded = False
        self.is_available = self._check_winget()
        self._active_procs: list[subprocess.Popen] = []
        self._cancel_requested = False
        self._lock = threading.Lock()
        self._outdated_ids: set[str] = set()
        self._load_callbacks: list = []

        if self.is_available:
            threading.Thread(target=self._load_installed_apps, daemon=True).start()
        else:
            self.is_loaded = True

    def on_loaded(self, callback):
        if self.is_loaded:
            callback()
        else:
            self._load_callbacks.append(callback)

    def _rebuild_outdated_cache(self):
        self._outdated_ids = {
            app_id for app_id, data in self.installed_apps.items() if data.get("available")
        }

    def is_outdated(self, app_id: str) -> bool:
        return app_id.lower() in self._outdated_ids

    def _check_winget(self) -> bool:
        try:
            result = subprocess.run(
                ["winget", "--version"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=15,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _load_installed_apps(self):
        try:
            result = subprocess.run(
                ["winget", "list", "--accept-source-agreements"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            lines = result.stdout.split("\n")
            start_parsing = False
            for line in lines:
                if line.startswith("---"):
                    start_parsing = True
                    continue
                if start_parsing and line.strip():
                    parts = re.split(r"\s{2,}", line.strip())
                    if len(parts) >= 3:
                        app_id = parts[1].lower()
                        version = parts[2]
                        available = None
                        if len(parts) > 4 and parts[4] == "winget":
                            available = parts[3]
                        elif len(parts) == 4 and parts[3] != "winget" and parts[2] != parts[3]:
                            available = parts[3]
                        self.installed_apps[app_id] = {
                            "version": version,
                            "available": available,
                        }
        except Exception as e:
            print("Error cargando winget list:", e)
        finally:
            self.is_loaded = True
            self._rebuild_outdated_cache()
            callbacks = list(self._load_callbacks)
            self._load_callbacks.clear()
            for cb in callbacks:
                try:
                    cb()
                except Exception:
                    pass

    def refresh_installed(self):
        """Recarga la lista de apps instaladas."""
        self.is_loaded = False
        self.installed_apps = {}
        if self.is_available:
            threading.Thread(target=self._load_installed_apps, daemon=True).start()

    def get_app_info(self, app_id):
        if not self.is_available:
            return {"status": "unavailable"}
        if not self.is_loaded:
            return {"status": "loading"}
        app_id_lower = app_id.lower()
        if app_id_lower in self.installed_apps:
            data = self.installed_apps[app_id_lower]
            return {
                "status": "installed",
                "version": data["version"],
                "available": data["available"],
            }
        return {"status": "not_installed"}

    def count_updates_in_apps(self, app_ids: list[str]) -> int:
        if not self.is_loaded or not self.is_available:
            return 0
        return sum(1 for app_id in app_ids if app_id.lower() in self._outdated_ids)

    def count_all_outdated(self, app_ids: list[str]) -> int:
        return self.count_updates_in_apps(app_ids)

    def cancel_active(self):
        self._cancel_requested = True
        with self._lock:
            for proc in self._active_procs:
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._active_procs.clear()

    def _run_winget_process(self, args, on_log=None):
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        with self._lock:
            self._active_procs.append(proc)
        last_line = ""
        try:
            for raw in proc.stdout:
                if self._cancel_requested:
                    proc.terminate()
                    break
                line = raw.rstrip()
                if line:
                    last_line = line
                    if on_log:
                        on_log(line)
            proc.wait()
            ok = proc.returncode == 0 and not self._cancel_requested
        except Exception as exc:
            if on_log:
                on_log(f"  ❌ Excepción: {exc}")
            ok = False
            last_line = str(exc)
        finally:
            with self._lock:
                if proc in self._active_procs:
                    self._active_procs.remove(proc)
        return ok, last_line

    def install_apps(self, app_ids, on_progress=None, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            results = []
            total = len(app_ids)
            for idx, app_id in enumerate(app_ids):
                if self._cancel_requested:
                    break
                if on_progress:
                    on_progress(idx, total, app_id)
                if on_log:
                    on_log(f"\n▶ Instalando {app_id}  ({idx + 1}/{total})…\n")

                ok, last_line = self._run_winget_process(
                    [
                        "winget", "install",
                        "--id", app_id,
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                        "--silent", "-e",
                        "--disable-interactivity",
                    ],
                    on_log=on_log,
                )
                label = "✅ OK" if ok else ("⚠️ Cancelado" if self._cancel_requested else "❌ Falló")
                if on_log:
                    on_log(f"  {label} — {app_id}\n")
                results.append({"id": app_id, "ok": ok, "msg": last_line})

            if on_progress:
                on_progress(total, total, "")
            if on_done:
                on_done(results)
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()

    def upgrade_apps(self, app_ids, on_progress=None, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            results = []
            total = len(app_ids)
            for idx, app_id in enumerate(app_ids):
                if self._cancel_requested:
                    break
                if on_progress:
                    on_progress(idx, total, app_id)
                if on_log:
                    on_log(f"\n▶ Actualizando {app_id}  ({idx + 1}/{total})…\n")
                ok, last_line = self._run_winget_process(
                    [
                        "winget", "upgrade",
                        "--id", app_id,
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                        "--silent", "-e",
                        "--disable-interactivity",
                    ],
                    on_log=on_log,
                )
                label = "✅ OK" if ok else ("⚠️ Cancelado" if self._cancel_requested else "❌ Falló")
                if on_log:
                    on_log(f"  {label} — {app_id}\n")
                results.append({"id": app_id, "ok": ok, "msg": last_line})
            if on_progress:
                on_progress(total, total, "")
            if on_done:
                on_done(results)
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()

    def uninstall_app(self, app_id, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            if on_log:
                on_log(f"\n▶ Desinstalando {app_id}…\n")
            ok, last_line = self._run_winget_process(
                [
                    "winget", "uninstall",
                    "--id", app_id,
                    "--silent", "-e",
                    "--disable-interactivity",
                ],
                on_log=on_log,
            )
            if on_log:
                on_log(f"  {'✅ OK' if ok else '❌ Falló'} — {app_id}\n")
            if on_done:
                on_done({"id": app_id, "ok": ok, "msg": last_line})
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()
