import os
import re
import subprocess
import tempfile
import threading

# Versiones / canales que NO se instalan
_BETA_RE = re.compile(
    r"(?i)(alpha|beta|preview|\bpre\b|\brc\b|insider|\bdev\b|canary|nightly|experimental|unstable|snapshot|testing)"
)
_VERSION_LINE_RE = re.compile(r"^[\d][\d\w\.\-\+]*$")
_MSSTORE_ID_RE = re.compile(r"^(9N|XP)[A-Z0-9]", re.I)

_BLOCKED_PACKAGES: dict[str, str] = {
    "overwolf.curseforge": (
        "CurseForge en winget usa el canal Overwolf Beta. "
        "Usa la entrada CurseForge del Hub (descarga directa estable)."
    ),
    "wowup.cfbeta": "Paquete beta de WowUp — bloqueado.",
}

_BLOCKED_URL_PATTERNS = [
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
        self._source_cache: dict[str, str] = {}

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

    def check_package_available(self, app_id: str) -> dict:
        """Comprueba si el paquete existe en winget/msstore."""
        if app_id.lower() in _BLOCKED_PACKAGES:
            return {"available": False, "reason": _BLOCKED_PACKAGES[app_id.lower()]}
        source = self._resolve_source(app_id)
        ok, output = self._winget_show(app_id, source)
        if ok:
            return {"available": True, "source": source}
        alt = "msstore" if source == "winget" else "winget"
        ok2, _ = self._winget_show(app_id, alt)
        if ok2:
            return {"available": True, "source": alt}
        return {"available": False, "reason": "No encontrado en winget ni Microsoft Store"}

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
        manifest: dict = {"dependencies": []}
        name_m = re.search(r"^Found (.+?) \[", output, re.M)
        if name_m:
            manifest["name"] = name_m.group(1).strip()
        ver_m = re.search(r"^Version:\s*(.+)$", output, re.M)
        if ver_m:
            manifest["version"] = ver_m.group(1).strip()
        url_m = re.search(r"Installer Url:\s*(.+)$", output, re.M)
        if url_m:
            manifest["installer_url"] = url_m.group(1).strip()
        for dep in re.findall(r"Package Dependencies:\s*\n\s+(.+)", output):
            manifest["dependencies"].append(dep.strip())
        return manifest

    @staticmethod
    def _is_blocked_url(url: str) -> bool:
        return any(p.search(url or "") for p in _BLOCKED_URL_PATTERNS)

    def _resolve_source(self, app_id: str, hint: str | None = None) -> str:
        if hint in ("winget", "msstore"):
            return hint
        key = app_id.lower()
        if key in self._source_cache:
            return self._source_cache[key]
        if _MSSTORE_ID_RE.match(app_id):
            self._source_cache[key] = "msstore"
            return "msstore"
        ok, _ = self._winget_show(app_id, "winget")
        if ok:
            self._source_cache[key] = "winget"
            return "winget"
        ok, _ = self._winget_show(app_id, "msstore")
        source = "msstore" if ok else "winget"
        self._source_cache[key] = source
        return source

    def _winget_show(self, app_id: str, source: str) -> tuple[bool, str]:
        return self._run_winget_process(
            [
                "winget", "show", "--id", app_id, "-e",
                "--source", source, "--accept-source-agreements",
            ],
            collect_output=True,
        )

    def _validate_stable_package(self, app_id: str, source: str | None = None) -> tuple[bool, str, dict]:
        key = app_id.lower()
        if key in _BLOCKED_PACKAGES:
            return False, _BLOCKED_PACKAGES[key], {}

        src = self._resolve_source(app_id, source)
        ok, output = self._winget_show(app_id, src)
        if not ok:
            alt = "msstore" if src == "winget" else "winget"
            ok, output = self._winget_show(app_id, alt)
            if ok:
                src = alt
            else:
                return False, f"Paquete no encontrado: {app_id}", {}

        manifest = self._parse_manifest(output)
        manifest["source"] = src
        name = manifest.get("name", "")
        version = manifest.get("version", "")
        url = manifest.get("installer_url", "")

        if _BETA_RE.search(app_id) or _BETA_RE.search(name):
            return False, f"Canal beta detectado: {name or app_id}", manifest
        if version and _BETA_RE.search(version):
            return False, f"Versión beta detectada: {version}", manifest
        if url and self._is_blocked_url(url):
            return False, "URL de instalador beta/preview bloqueada", manifest

        stable = None
        if src == "winget":
            stable = self.get_latest_stable_version(app_id, src)
        if not stable and version and not _BETA_RE.search(version):
            stable = version
        if not stable and src == "msstore":
            stable = None  # msstore: sin pin de versión

        manifest["stable_version"] = stable
        return True, stable or version or "latest", manifest

    def get_latest_stable_version(self, app_id: str, source: str = "winget") -> str | None:
        key = f"{app_id.lower()}:{source}"
        if key in self._version_cache:
            return self._version_cache[key]

        stable = None
        ok, output = self._run_winget_process(
            [
                "winget", "show", "--id", app_id, "-e", "--versions",
                "--source", source, "--accept-source-agreements",
            ],
            collect_output=True,
        )
        if ok:
            for version in self._parse_versions(output):
                if not _BETA_RE.search(version):
                    stable = version
                    break

        self._version_cache[key] = stable
        return stable

    def _build_install_args(
        self,
        app_id: str,
        *,
        source: str,
        scope: str,
        silent: bool,
        version: str | None,
        force: bool,
        architecture: str | None = None,
        interactive: bool = False,
    ):
        args = [
            "winget", "install",
            "--id", app_id,
            "-e",
            "--source", source,
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--scope", scope,
        ]
        if version:
            args.extend(["--version", version])
        if architecture:
            args.extend(["--architecture", architecture])
        if silent and not interactive:
            args.append("--silent")
            args.append("--disable-interactivity")
        elif interactive:
            args.append("-i")
        else:
            args.append("--disable-interactivity")
        if force:
            args.append("--force")
        return args

    def _install_dependencies(self, app_id: str, source: str, on_log=None) -> bool:
        if on_log:
            on_log("  ↳ Instalando dependencias…")
        ok, output = self._run_winget_process(
            [
                "winget", "install", "--id", app_id, "-e",
                "--source", source,
                "--dependencies-only",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            on_log=on_log,
            collect_output=True,
        )
        return ok or self._install_succeeded(ok, output)

    def _install_with_retries(self, winget_id: str, display_name: str, opts: dict | None = None, on_log=None) -> tuple[bool, str]:
        opts = opts or {}
        prefer_silent = opts.get("install_silent", True)
        source_hint = opts.get("source")

        ok, msg, manifest = self._validate_stable_package(winget_id, source_hint)
        if not ok:
            if on_log:
                on_log(f"  ❌ {msg}")
            return False, msg

        source = manifest.get("source", "winget")
        stable = manifest.get("stable_version")
        if on_log:
            on_log(f"  ✓ Fuente: {source}")
            on_log(f"  ✓ Canal estable — {display_name}")
            if stable:
                on_log(f"  ✓ Versión objetivo: {stable}")
            if manifest.get("installer_url") and not self._is_blocked_url(manifest["installer_url"]):
                on_log(f"  ✓ Instalador: {manifest['installer_url'][:90]}…")

        if manifest.get("dependencies") and opts.get("install_dependencies", True):
            self._install_dependencies(winget_id, source, on_log=on_log)

        attempts = [
            {"scope": "user", "silent": prefer_silent, "version": stable, "force": False, "arch": "x64", "interactive": False, "label": "usuario + versión"},
            {"scope": "user", "silent": prefer_silent, "version": None, "force": False, "arch": "x64", "interactive": False, "label": "usuario + última"},
            {"scope": "user", "silent": prefer_silent, "version": None, "force": True, "arch": "x64", "interactive": False, "label": "usuario + forzar"},
            {"scope": "machine", "silent": prefer_silent, "version": None, "force": False, "arch": "x64", "interactive": False, "label": "sistema (admin)"},
            {"scope": "user", "silent": False, "version": None, "force": False, "arch": None, "interactive": True, "label": "interactivo (ventana)"},
        ]

        last_output = ""
        for attempt in attempts:
            if self._cancel_requested:
                break
            if on_log:
                on_log(f"  Intento ({attempt['label']})…")
            ok, output = self._run_winget_process(
                self._build_install_args(
                    winget_id,
                    source=source,
                    scope=attempt["scope"],
                    silent=attempt["silent"],
                    version=attempt["version"],
                    force=attempt["force"],
                    architecture=attempt["arch"],
                    interactive=attempt["interactive"],
                ),
                on_log=on_log,
                collect_output=True,
            )
            last_output = output
            if self._install_succeeded(ok, output):
                return True, output
            if "no applicable installer" in (output or "").lower() and attempt["version"]:
                continue

        return False, last_output or "Todos los intentos fallaron"

    def install_direct(self, url: str, display_name: str, on_log=None) -> tuple[bool, str]:
        """Descarga un instalador .exe/.msi y lo ejecuta (sin winget)."""
        if on_log:
            on_log(f"  ↳ Descarga directa (sin winget)…")
            on_log(f"  ✓ URL: {url[:100]}{'…' if len(url) > 100 else ''}")
        try:
            import requests

            resp = requests.get(
                url,
                timeout=180,
                stream=True,
                headers={"User-Agent": "ResetX/2.2.1"},
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
            if on_log:
                on_log(f"  ✓ Descargado ({total // 1024} KB): {path}")

            if on_log:
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
            return ok, f"Instalador finalizado (código {proc.returncode})"
        except Exception as exc:
            if on_log:
                on_log(f"  ❌ Descarga directa: {exc}")
            return False, str(exc)

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
                    "install_dependencies": spec.get("install_dependencies", True),
                    "source": spec.get("source"),
                }
                install_mode = spec.get("install_mode", "winget")
                download_url = spec.get("download_url")

                if on_progress:
                    on_progress(idx, total, catalog_id)
                if on_log:
                    on_log(f"\n▶ Instalando {name}  ({idx + 1}/{total})…")

                if install_mode == "direct" and download_url:
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
                self._version_cache.pop(f"{winget_id.lower()}:winget", None)
                self._version_cache.pop(f"{winget_id.lower()}:msstore", None)

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

                ok, msg, manifest = self._validate_stable_package(winget_id, spec.get("source"))
                if not ok:
                    if on_log:
                        on_log(f"  ❌ {msg}")
                    results.append({"id": catalog_id, "ok": False, "msg": msg})
                    continue

                source = manifest.get("source", "winget")
                stable = manifest.get("stable_version")
                if on_log and stable:
                    on_log(f"  ✓ Versión estable: {stable}")

                args = [
                    "winget", "upgrade", "--id", winget_id, "-e",
                    "--source", source,
                    "--accept-package-agreements", "--accept-source-agreements",
                    "--disable-interactivity", "--silent",
                ]
                if stable:
                    args.extend(["--version", stable])

                ok, last_line = self._run_winget_process(args, on_log=on_log, collect_output=True)
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

    def uninstall_app(self, app_id, on_log=None, on_done=None):
        def _worker():
            self._cancel_requested = False
            source = self._resolve_source(app_id)
            if on_log:
                on_log(f"\n▶ Desinstalando {app_id}…\n")
            ok, last_line = self._run_winget_process(
                [
                    "winget", "uninstall", "--id", app_id, "-e",
                    "--source", source, "--silent", "--disable-interactivity",
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
