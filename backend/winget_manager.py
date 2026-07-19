import re
import subprocess
import threading

# Versiones / canales que NO se instalan
_BETA_RE = re.compile(
    r"(?i)(alpha|beta|preview|\bpre\b|\brc\b|insider|\bdev\b|canary|nightly|experimental|unstable|snapshot|testing)"
)
_VERSION_LINE_RE = re.compile(r"^[\d][\d\w\.\-\+]*$")

# Paquetes winget que instalan producto beta aunque la versión no lo diga
_BLOCKED_PACKAGES: dict[str, str] = {
    "overwolf.curseforge": (
        "CurseForge en winget instala la app Beta de Overwolf. "
        "Usa Modrinth o Prism Launcher (estables) desde el Hub."
    ),
    "wowup.cfbeta": "Paquete beta de WowUp — bloqueado.",
}

# URLs de instalador conocidas como canal beta/preview
_BLOCKED_URL_PATTERNS = [
    re.compile(r"curseforge-latest-win64\.exe", re.I),
    re.compile(r"/beta/", re.I),
    re.compile(r"/preview/", re.I),
    re.compile(r"/insider/", re.I),
    re.compile(r"/canary/", re.I),
    re.compile(r"/nightly/", re.I),
]


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
        self._version_cache: dict[str, str | None] = {}

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
        )
        return any(m in lower for m in success_markers)

    @staticmethod
    def _parse_versions(output: str) -> list[str]:
        versions: list[str] = []
        for line in output.splitlines():
            token = line.strip()
            if _VERSION_LINE_RE.match(token):
                versions.append(token)
        return versions

    @staticmethod
    def _parse_manifest(output: str) -> dict:
        manifest: dict = {}
        name_m = re.search(r"^Found (.+?) \[", output, re.M)
        if name_m:
            manifest["name"] = name_m.group(1).strip()
        ver_m = re.search(r"^Version:\s*(.+)$", output, re.M)
        if ver_m:
            manifest["version"] = ver_m.group(1).strip()
        url_m = re.search(r"Installer Url:\s*(.+)$", output, re.M)
        if url_m:
            manifest["installer_url"] = url_m.group(1).strip()
        return manifest

    @staticmethod
    def _is_blocked_url(url: str) -> bool:
        return any(p.search(url or "") for p in _BLOCKED_URL_PATTERNS)

    def _validate_stable_package(self, app_id: str) -> tuple[bool, str, dict]:
        key = app_id.lower()
        if key in _BLOCKED_PACKAGES:
            return False, _BLOCKED_PACKAGES[key], {}

        ok, output = self._run_winget_process(
            [
                "winget", "show",
                "--id", app_id,
                "-e",
                "--source", "winget",
                "--accept-source-agreements",
            ],
            collect_output=True,
        )
        if not ok:
            return False, f"Paquete no encontrado en winget: {app_id}", {}

        manifest = self._parse_manifest(output)
        name = manifest.get("name", "")
        version = manifest.get("version", "")
        url = manifest.get("installer_url", "")

        if _BETA_RE.search(app_id) or _BETA_RE.search(name):
            return False, f"Canal beta detectado en el paquete: {name or app_id}", manifest
        if _BETA_RE.search(version):
            return False, f"Versión beta detectada: {version}", manifest
        if url and self._is_blocked_url(url):
            return False, "URL de instalador de canal beta/preview bloqueada", manifest

        stable = self.get_latest_stable_version(app_id)
        if not stable:
            return False, "No se encontró versión estable en winget", manifest

        manifest["stable_version"] = stable
        return True, stable, manifest

    def get_latest_stable_version(self, app_id: str) -> str | None:
        key = app_id.lower()
        if key in self._version_cache:
            return self._version_cache[key]

        stable = None
        try:
            ok, output = self._run_winget_process(
                [
                    "winget", "show",
                    "--id", app_id,
                    "-e",
                    "--versions",
                    "--source", "winget",
                    "--accept-source-agreements",
                ],
                collect_output=True,
            )
            if ok:
                for version in self._parse_versions(output):
                    if not _BETA_RE.search(version):
                        stable = version
                        break
        except Exception:
            pass

        self._version_cache[key] = stable
        return stable

    def _build_install_args(self, app_id: str, *, scope: str, silent: bool, version: str | None, force: bool):
        args = [
            "winget", "install",
            "--id", app_id,
            "-e",
            "--source", "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
            "--scope", scope,
        ]
        if version:
            args.extend(["--version", version])
        if silent:
            args.append("--silent")
        if force:
            args.append("--force")
        return args

    def _install_with_retries(self, winget_id: str, display_name: str, on_log=None) -> tuple[bool, str]:
        ok, msg, manifest = self._validate_stable_package(winget_id)
        if not ok:
            if on_log:
                on_log(f"  ❌ {msg}")
            return False, msg

        stable = manifest["stable_version"]
        if on_log:
            on_log(f"  ✓ Canal estable — {display_name}")
            on_log(f"  ✓ Versión estable: {stable}")
            if manifest.get("installer_url") and not self._is_blocked_url(manifest["installer_url"]):
                on_log(f"  ✓ Instalador: {manifest['installer_url'][:90]}…")

        attempts = [
            {"scope": "user", "silent": True, "version": stable, "force": False, "label": "usuario"},
            {"scope": "user", "silent": True, "version": stable, "force": True, "label": "usuario (forzar)"},
            {"scope": "machine", "silent": True, "version": stable, "force": False, "label": "sistema"},
            {"scope": "user", "silent": False, "version": stable, "force": False, "label": "interactivo"},
        ]

        last_output = ""
        for attempt in attempts:
            if self._cancel_requested:
                break
            if on_log:
                on_log(f"  Intento ({attempt['label']})…")
            ok, output = self._run_winget_process(
                self._build_install_args(winget_id, **{k: attempt[k] for k in ("scope", "silent", "version", "force")}),
                on_log=on_log,
                collect_output=True,
            )
            last_output = output
            if self._install_succeeded(ok, output):
                return True, output

        return False, last_output

    def install_apps(self, app_specs, on_progress=None, on_log=None, on_done=None):
        """app_specs: list of dicts con catalog_id, winget_id, name."""

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

                if on_progress:
                    on_progress(idx, total, catalog_id)
                if on_log:
                    on_log(f"\n▶ Instalando {name}  ({idx + 1}/{total})…")
                    on_log(f"  ID winget: {winget_id}")

                ok, last_line = self._install_with_retries(winget_id, name, on_log=on_log)
                label = "✅ OK" if ok else ("⚠️ Cancelado" if self._cancel_requested else "❌ Falló")
                if on_log:
                    on_log(f"  {label} — {name}\n")
                results.append({"id": catalog_id, "ok": ok, "msg": last_line})
                self._version_cache.pop(winget_id.lower(), None)

            if on_progress:
                on_progress(total, total, "")
            if on_done:
                on_done(results)
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()

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

                if on_progress:
                    on_progress(idx, total, catalog_id)
                if on_log:
                    on_log(f"\n▶ Actualizando {name}  ({idx + 1}/{total})…")

                ok, msg, manifest = self._validate_stable_package(winget_id)
                if not ok:
                    if on_log:
                        on_log(f"  ❌ {msg}")
                    results.append({"id": catalog_id, "ok": False, "msg": msg})
                    continue

                stable = manifest["stable_version"]
                if on_log:
                    on_log(f"  ✓ Versión estable: {stable}")

                args = [
                    "winget", "upgrade",
                    "--id", winget_id,
                    "-e",
                    "--source", "winget",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--disable-interactivity",
                    "--silent",
                    "--version", stable,
                ]
                ok, last_line = self._run_winget_process(args, on_log=on_log, collect_output=True)
                ok = self._install_succeeded(ok, last_line)
                label = "✅ OK" if ok else ("⚠️ Cancelado" if self._cancel_requested else "❌ Falló")
                if on_log:
                    on_log(f"  {label} — {name}\n")
                results.append({"id": catalog_id, "ok": ok, "msg": last_line})
                self._version_cache.pop(winget_id.lower(), None)

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
                    "-e",
                    "--source", "winget",
                    "--silent",
                    "--disable-interactivity",
                ],
                on_log=on_log,
                collect_output=True,
            )
            ok = self._install_succeeded(ok, last_line)
            if on_log:
                on_log(f"  {'✅ OK' if ok else '❌ Falló'} — {app_id}\n")
            if on_done:
                on_done({"id": app_id, "ok": ok, "msg": last_line})
            self.refresh_installed()

        threading.Thread(target=_worker, daemon=True).start()
