import os
import re
import subprocess
import tempfile
import threading

_BETA_ID_RE = re.compile(r"(?i)(\.beta|\.preview|\.insider|\.canary|\.nightly|cfbeta)")
_MSSTORE_ID_RE = re.compile(r"^(9N|XP)[A-Z0-9]", re.I)

CREATE_NEW_CONSOLE = 0x00000010

_BLOCKED_PACKAGES: dict[str, str] = {
    "overwolf.curseforge": (
        "CurseForge en winget usa el canal Overwolf Beta. "
        "Usa la entrada CurseForge del Hub (descarga directa estable)."
    ),
    "wowup.cfbeta": "Paquete beta de WowUp — bloqueado.",
}


class WingetManager:
    def __init__(self):
        self.installed_apps: dict[str, dict] = {}
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

    # ──────────────────────────────────────────────────────────────────────
    # Callbacks / state
    # ──────────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────────
    # Winget availability & installed list
    # ──────────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────────
    # Process management
    # ──────────────────────────────────────────────────────────────────────

    def cancel_active(self):
        self._cancel_requested = True
        with self._lock:
            for proc in self._active_procs:
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._active_procs.clear()

    def _run_winget_process(self, args, on_log=None, collect_output=False):
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
        lines: list[str] = []
        last_line = ""
        try:
            for raw in proc.stdout:
                if self._cancel_requested:
                    proc.terminate()
                    break
                line = raw.rstrip()
                if line:
                    last_line = line
                    lines.append(line)
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
        output = "\n".join(lines) if collect_output else last_line
        return ok, output

    @staticmethod
    def _install_succeeded(ok: bool, output: str) -> bool:
        if ok:
            return True
        lower = (output or "").lower()
        success_markers = (
            "already installed",
            "ya está instalado",
            "ya esta instalado",
            "no se encontraron actualizaciones",
            "no applicable update",
            "no available upgrade found",
            "no hay actualizaciones disponibles",
            "successfully installed",
            "instalación correcta",
            "instalacion correcta",
            "successfully uninstalled",
            "desinstalación correcta",
            "desinstalacion correcta",
            "uninstalled successfully",
        )
        return any(m in lower for m in success_markers)

    # ──────────────────────────────────────────────────────────────────────
    # Post-install verification
    # ──────────────────────────────────────────────────────────────────────

    def _verify_installed(self, app_id: str, on_log=None) -> bool:
        ok, output = self._run_winget_process(
            ["winget", "list", "--id", app_id, "-e", "--accept-source-agreements"],
            collect_output=True,
        )
        installed = ok and app_id.lower() in output.lower()
        if on_log:
            if installed:
                on_log(f"  ✓ Verificado: {app_id} está instalado")
            else:
                on_log(f"  ⚠ No se pudo verificar la instalación de {app_id}")
        return installed

    # ──────────────────────────────────────────────────────────────────────
    # Install via winget (simplified chain)
    # ──────────────────────────────────────────────────────────────────────

    def _is_blocked(self, app_id: str) -> tuple[bool, str]:
        key = app_id.lower()
        if key in _BLOCKED_PACKAGES:
            return True, _BLOCKED_PACKAGES[key]
        if _BETA_ID_RE.search(app_id):
            return True, f"Paquete beta/preview detectado en ID: {app_id}"
        return False, ""

    def _resolve_source(self, app_id: str, hint: str | None = None) -> str:
        if hint in ("winget", "msstore"):
            return hint
        if _MSSTORE_ID_RE.match(app_id):
            return "msstore"
        return "winget"

    def _install_with_retries(self, winget_id: str, display_name: str, opts: dict | None = None, on_log=None) -> tuple[bool, str]:
        opts = opts or {}
        prefer_silent = opts.get("install_silent", True)
        source = self._resolve_source(winget_id, opts.get("source"))

        blocked, reason = self._is_blocked(winget_id)
        if blocked:
            if on_log:
                on_log(f"  ❌ {reason}")
            return False, reason

        if on_log:
            on_log(f"  ✓ Fuente: {source}")

        attempts = [
            {"scope": "user", "silent": prefer_silent, "label": "usuario + silencioso"},
            {"scope": "machine", "silent": prefer_silent, "label": "sistema + silencioso"},
            {"scope": "user", "silent": False, "label": "usuario + interactivo"},
        ]

        last_output = ""
        for attempt in attempts:
            if self._cancel_requested:
                break
            if on_log:
                on_log(f"  Intento ({attempt['label']})…")

            args = [
                "winget", "install",
                "--id", winget_id, "-e",
                "--source", source,
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--scope", attempt["scope"],
            ]
            if attempt["silent"]:
                args.extend(["--silent", "--disable-interactivity"])
            else:
                args.append("-i")

            ok, output = self._run_winget_process(args, on_log=on_log, collect_output=True)
            last_output = output
            if self._install_succeeded(ok, output):
                self._verify_installed(winget_id, on_log=on_log)
                return True, output

        return False, last_output or "Todos los intentos de instalación fallaron"

    # ──────────────────────────────────────────────────────────────────────
    # Direct download install
    # ──────────────────────────────────────────────────────────────────────

    def install_direct(self, url: str, display_name: str, on_log=None) -> tuple[bool, str]:
        if on_log:
            on_log(f"  ↳ Descarga directa (sin winget)…")
            on_log(f"  ✓ URL: {url[:100]}{'…' if len(url) > 100 else ''}")
        try:
            import requests

            resp = requests.get(
                url,
                timeout=180,
                stream=True,
                headers={"User-Agent": "ResetX/2.3.0"},
                allow_redirects=True,
            )
            resp.raise_for_status()
            lower = url.lower()
            if lower.endswith(".msi"):
                suffix = ".msi"
            elif lower.endswith(".msix") or lower.endswith(".appx"):
                suffix = ".msix"
            else:
                suffix = ".exe"
            fd, path = tempfile.mkstemp(suffix=suffix, prefix="resetx_install_")
            os.close(fd)
            total = 0
            with open(path, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if self._cancel_requested:
                        break
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            if self._cancel_requested:
                return False, "Cancelado"

            if total < 102400:
                if on_log:
                    on_log(f"  ❌ Archivo demasiado pequeño ({total} bytes) — probablemente una página de error")
                return False, f"Descarga inválida: solo {total} bytes (mínimo 100KB)"

            if on_log:
                on_log(f"  ✓ Descargado ({total // 1024} KB): {path}")
                on_log("  ↳ Ejecutando instalador (sigue las ventanas que aparezcan)…")

            if suffix == ".msi":
                args = ["msiexec.exe", "/i", path]
            else:
                args = [path]
            proc = subprocess.Popen(args, creationflags=CREATE_NEW_CONSOLE)
            with self._lock:
                self._active_procs.append(proc)
            proc.wait()
            with self._lock:
                if proc in self._active_procs:
                    self._active_procs.remove(proc)
            ok = proc.returncode in (0, 3010, 1641)
            if not ok and on_log:
                on_log(f"  ❌ Instalador terminó con código {proc.returncode}")
            return ok, f"Instalador finalizado (código {proc.returncode})"
        except Exception as exc:
            if on_log:
                on_log(f"  ❌ Descarga directa: {exc}")
            return False, str(exc)

    # ──────────────────────────────────────────────────────────────────────
    # Office C2R install
    # ──────────────────────────────────────────────────────────────────────

    def install_office(self, display_name: str, on_log=None, product_id: str | None = None) -> tuple[bool, str]:
        from backend.office_installer import install_office_c2r

        return install_office_c2r(
            on_log,
            cancel_check=lambda: self._cancel_requested,
            product_id=product_id or "O365ProPlusRetail",
        )

    # ──────────────────────────────────────────────────────────────────────
    # Batch install
    # ──────────────────────────────────────────────────────────────────────

    def install_apps(self, app_specs, on_progress=None, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            results = []
            total = len(app_specs)
            for idx, spec in enumerate(app_specs):
                if self._cancel_requested:
                    break
                winget_id = spec.get("winget_id") or spec.get("catalog_id") or spec.get("id")
                catalog_id = spec.get("catalog_id") or winget_id
                name = spec.get("name") or winget_id
                opts = {
                    "install_silent": spec.get("install_silent", True),
                    "source": spec.get("source"),
                }
                install_mode = spec.get("install_mode", "winget")
                download_url = spec.get("download_url")

                if on_progress:
                    on_progress(idx, total, catalog_id)
                if on_log:
                    on_log(f"\n▶ Instalando {name}  ({idx + 1}/{total})…")

                if install_mode == "office_c2r":
                    if on_log:
                        on_log(f"  Modo: Office C2R (instalador oficial Microsoft)")
                    ok, last_line = self.install_office(
                        name, on_log=on_log, product_id=spec.get("office_product")
                    )
                elif install_mode == "direct" and download_url:
                    if on_log:
                        on_log(f"  Modo: descarga directa")
                    ok, last_line = self.install_direct(download_url, name, on_log=on_log)
                else:
                    if on_log:
                        on_log(f"  ID winget: {winget_id}")
                    ok, last_line = self._install_with_retries(winget_id, name, opts, on_log=on_log)
                    if not ok and download_url:
                        if on_log:
                            on_log("  ↳ Winget falló — probando descarga directa…")
                        ok2, last2 = self.install_direct(download_url, name, on_log=on_log)
                        if ok2:
                            ok, last_line = ok2, last2

                label = "✅ OK" if ok else ("⚠️ Cancelado" if self._cancel_requested else "❌ Falló")
                if on_log:
                    on_log(f"  {label} — {name}\n")
                results.append({
                    "id": catalog_id,
                    "ok": ok,
                    "msg": last_line,
                    "download_page": spec.get("download_page"),
                    "download_url": download_url if not ok else None,
                })

            if on_progress:
                on_progress(total, total, "")
            if on_done:
                on_done(results)
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # Upgrade
    # ──────────────────────────────────────────────────────────────────────

    def upgrade_apps(self, app_specs, on_progress=None, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            results = []
            total = len(app_specs)
            for idx, spec in enumerate(app_specs):
                if self._cancel_requested:
                    break
                winget_id = spec.get("winget_id") or spec.get("catalog_id") or spec.get("id")
                catalog_id = spec.get("catalog_id") or winget_id
                name = spec.get("name") or winget_id
                source = self._resolve_source(winget_id, spec.get("source"))

                if on_progress:
                    on_progress(idx, total, catalog_id)
                if on_log:
                    on_log(f"\n▶ Actualizando {name}  ({idx + 1}/{total})…")
                    on_log(f"  ✓ Fuente: {source}")

                args = [
                    "winget", "upgrade", "--id", winget_id, "-e",
                    "--source", source,
                    "--accept-package-agreements", "--accept-source-agreements",
                    "--disable-interactivity", "--silent",
                ]
                ok, last_line = self._run_winget_process(args, on_log=on_log, collect_output=True)
                ok = self._install_succeeded(ok, last_line)

                if not ok:
                    if on_log:
                        on_log(f"  Reintento con --scope machine…")
                    args_machine = args + ["--scope", "machine"]
                    ok, last_line = self._run_winget_process(args_machine, on_log=on_log, collect_output=True)
                    ok = self._install_succeeded(ok, last_line)

                label = "✅ OK" if ok else ("⚠️ Cancelado" if self._cancel_requested else "❌ Falló")
                if on_log:
                    on_log(f"  {label} — {name}\n")
                results.append({"id": catalog_id, "ok": ok, "msg": last_line})

            if on_progress:
                on_progress(total, total, "")
            if on_done:
                on_done(results)
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # Uninstall (with retries + deelevated)
    # ──────────────────────────────────────────────────────────────────────

    def uninstall_app(self, app_id, display_name: str | None = None, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            name = display_name or app_id
            if on_log:
                on_log(f"\n▶ Desinstalando {name}…")
                on_log(f"  ID winget: {app_id}")
            ok, last_line = self._uninstall_with_retries(app_id, name, on_log=on_log)
            if on_log:
                on_log(f"  {'✅ OK — desinstalado por completo' if ok else '❌ Falló'} — {name}\n")
            if on_done:
                on_done({"id": app_id, "ok": ok, "msg": last_line})
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()

    def _build_uninstall_args(
        self,
        app_id: str,
        *,
        source: str,
        scope: str,
        purge: bool = True,
        force: bool = False,
        silent: bool = True,
    ) -> list[str]:
        args = [
            "winget", "uninstall", "--id", app_id, "-e",
            "--source", source,
            "--scope", scope,
            "--accept-source-agreements",
        ]
        if silent:
            args.extend(["--silent", "--disable-interactivity"])
        if purge:
            args.append("--purge")
        if force:
            args.append("--force")
        return args

    def _run_deelevated_winget(self, winget_args: list[str], on_log=None) -> tuple[bool, str]:
        if on_log:
            on_log("  ↳ Reintento en contexto de usuario (sin admin)…")
        winget_line = subprocess.list2cmdline(winget_args)
        cmd = f'runas /trustlevel:0x20000 {winget_line}'
        return self._run_winget_process(["cmd", "/c", cmd], on_log=on_log, collect_output=True)

    def _uninstall_with_retries(self, app_id: str, display_name: str, on_log=None) -> tuple[bool, str]:
        source = self._resolve_source(app_id)
        if on_log:
            on_log(f"  ✓ Fuente: {source}")

        attempts = [
            {"scope": "user", "purge": True, "force": False, "deelevated": False, "label": "usuario + purge"},
            {"scope": "machine", "purge": True, "force": False, "deelevated": False, "label": "sistema + purge"},
            {"scope": "user", "purge": True, "force": True, "deelevated": False, "label": "usuario + forzar"},
            {"scope": "user", "purge": True, "force": True, "deelevated": True, "label": "usuario sin admin"},
        ]

        last_output = ""
        admin_block = "cannot be uninstalled when running with administrator"

        for attempt in attempts:
            if self._cancel_requested:
                break
            if on_log:
                on_log(f"  Intento ({attempt['label']})…")
            args = self._build_uninstall_args(
                app_id,
                source=source,
                scope=attempt["scope"],
                purge=attempt["purge"],
                force=attempt["force"],
            )
            if attempt["deelevated"]:
                ok, output = self._run_deelevated_winget(args, on_log=on_log)
            else:
                ok, output = self._run_winget_process(args, on_log=on_log, collect_output=True)
            last_output = output
            if self._install_succeeded(ok, output):
                return True, output
            lower = (output or "").lower()
            if admin_block in lower and not attempt["deelevated"]:
                continue
            if "no installed package found" in lower:
                return True, "Ya no estaba instalado"

        return False, last_output or "Todos los intentos de desinstalación fallaron"
