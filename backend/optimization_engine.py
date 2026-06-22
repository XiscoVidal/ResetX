import ctypes
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from backend.utils import get_base_path

STATE_FILE = os.path.join(get_base_path(), "data", "tweak_state.json")


@dataclass
class TweakResult:
    tweak_id: str
    status: str  # ok | error | skipped
    message: str = ""


# Metadatos para UI y revert
TWEAK_META: dict[str, dict] = {
    "restore_point": {"label": "Punto de restauración", "revertable": False, "admin": True},
    "telemetry": {"label": "Bloquear telemetría", "revertable": True, "admin": True},
    "telemetry_extra": {"label": "Servicios telemetría extra", "revertable": True, "admin": True},
    "power_plan": {"label": "Plan Ultimate Performance", "revertable": True, "admin": False},
    "power_fine": {"label": "Ajustes finos de energía", "revertable": True, "admin": False},
    "temp": {"label": "Limpieza temporal profunda", "revertable": False, "admin": True},
    "visual_effects": {"label": "Efectos visuales rendimiento", "revertable": True, "admin": False},
    "disk_optimize": {"label": "Optimización de discos", "revertable": False, "admin": True},
    "standby_ram": {"label": "Vaciar standby list", "revertable": False, "admin": True},
    "gaming": {"label": "Tweaks gaming", "revertable": True, "admin": False},
    "game_mode": {"label": "Game Mode", "revertable": True, "admin": False},
    "hags": {"label": "HAGS", "revertable": True, "admin": True},
    "mmcss": {"label": "MMCSS juegos", "revertable": True, "admin": True},
    "mouse_precision": {"label": "Mouse 1:1", "revertable": True, "admin": False},
    "vbs": {"label": "Desactivar VBS/HVCI", "revertable": False, "admin": True},
    "core_parking": {"label": "Core parking off", "revertable": True, "admin": False},
    "windowed_opt": {"label": "Windowed optimizations", "revertable": True, "admin": False},
    "auto_maintenance": {"label": "Mantenimiento auto off", "revertable": True, "admin": True},
    "power_throttling": {"label": "Power throttling off", "revertable": True, "admin": True},
    "delivery_opt": {"label": "Delivery Optimization off", "revertable": True, "admin": True},
    "network": {"label": "Flush DNS + Winsock", "revertable": False, "admin": True},
    "dns_custom": {"label": "DNS 8.8.8.8 / 1.1.1.1", "revertable": True, "admin": True},
    "services": {"label": "SysMain / WSearch off", "revertable": True, "admin": True},
    "startup": {"label": "Inicio de terceros off", "revertable": True, "admin": True},
    "fast_startup": {"label": "Arranque rápido", "revertable": True, "admin": True},
    "tips_suggestions": {"label": "Tips y sugerencias off", "revertable": True, "admin": False},
    "hibernate_off": {"label": "Desactivar hibernación", "revertable": True, "admin": True},
    "ntfs_optimize": {"label": "NTFS sin last access", "revertable": True, "admin": True},
    "background_apps": {"label": "Apps segundo plano off", "revertable": True, "admin": False},
    "widgets_off": {"label": "Widgets Windows off", "revertable": True, "admin": True},
    "fullscreen_opt": {"label": "Fullscreen optimizations off", "revertable": True, "admin": False},
    "tcp_optimize": {"label": "TCP baja latencia", "revertable": True, "admin": True},
}

TWEAK_ORDER = list(TWEAK_META.keys())
REVERTABLE = {k for k, v in TWEAK_META.items() if v.get("revertable")}


class OptimizationEngine:
    def __init__(
        self,
        callback_log: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        on_tweak_status: Optional[Callable] = None,
        on_tweak_result: Optional[Callable] = None,
        on_done: Optional[Callable] = None,
    ):
        self.callback_log = callback_log
        self.on_progress = on_progress
        self.on_tweak_status = on_tweak_status
        self.on_tweak_result = on_tweak_result
        self.on_done = on_done
        self._admin: Optional[bool] = None

    def log(self, message: str):
        if self.callback_log:
            self.callback_log(message)

    @staticmethod
    def is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _needs_admin(self, tweak_id: str) -> bool:
        return TWEAK_META.get(tweak_id, {}).get("admin", False)

    def _load_state(self) -> dict:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_state(self, state: dict):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _mark_applied(self, tweak_id: str, backup: Optional[dict] = None):
        state = self._load_state()
        entry = {"applied_at": datetime.now(timezone.utc).isoformat(), "backup": backup or {}}
        state[tweak_id] = entry
        self._save_state(state)

    def _mark_reverted(self, tweak_id: str):
        state = self._load_state()
        state.pop(tweak_id, None)
        self._save_state(state)

    def get_applied_tweaks(self) -> list[str]:
        return list(self._load_state().keys())

    def get_tweak_backup(self, tweak_id: str) -> dict:
        return self._load_state().get(tweak_id, {}).get("backup", {})

    def execute_powershell(self, command: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            combined = out if out else err
            return result.returncode == 0, combined
        except Exception as e:
            return False, str(e)

    def query_powershell(self, command: str) -> str:
        ok, out = self.execute_powershell(command)
        return out if ok else ""

    def _status(self, tweak_id: str, status: str):
        if self.on_tweak_status:
            self.on_tweak_status(tweak_id, status)

    def _result(self, result: TweakResult):
        tag = {"ok": "[OK]", "error": "[ERROR]", "skipped": "[WARN]"}.get(result.status, "")
        self.log(f" {tag} {TWEAK_META.get(result.tweak_id, {}).get('label', result.tweak_id)}"
                 + (f" — {result.message}" if result.message else ""))
        if self.on_tweak_result:
            self.on_tweak_result(result)
        self._status(result.tweak_id, "ok" if result.status == "ok" else "error" if result.status == "error" else "skipped")

    def _capture_dns_backup(self) -> dict:
        script = (
            "$a = Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1; "
            "if ($a) { "
            "  $dns = (Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4).ServerAddresses -join ','; "
            "  Write-Output ($a.ifIndex.ToString() + '|' + $dns) "
            "}"
        )
        raw = self.query_powershell(script)
        if "|" in raw:
            idx, dns = raw.split("|", 1)
            return {"ifIndex": idx.strip(), "dns": dns.strip()}
        return {}

    def _verify_service_disabled(self, name: str) -> bool:
        out = self.query_powershell(f"(Get-Service -Name {name} -ErrorAction SilentlyContinue).StartType")
        return "disabled" in out.lower()

    def _verify_service_running_type(self, name: str, start_type: str) -> bool:
        out = self.query_powershell(f"(Get-Service -Name {name} -ErrorAction SilentlyContinue).StartType")
        return start_type.lower() in out.lower()

    def _apply_tweak(self, tweak_id: str, options: dict) -> TweakResult:
        label = TWEAK_META.get(tweak_id, {}).get("label", tweak_id)
        self._status(tweak_id, "running")
        self.log(f" -> {label}…")

        if self._needs_admin(tweak_id) and not self.is_admin():
            return TweakResult(tweak_id, "skipped", "Requiere permisos de administrador")

        try:
            handler = getattr(self, f"_tweak_{tweak_id}", None)
            if handler is None:
                return TweakResult(tweak_id, "skipped", "Tweak no implementado")
            return handler(options)
        except Exception as e:
            return TweakResult(tweak_id, "error", str(e))

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _tweak_restore_point(self, _o) -> TweakResult:
        ok, _ = self.execute_powershell(
            "Enable-ComputerRestore -Drive 'C:\\'; "
            "Checkpoint-Computer -Description 'ResetX - Pre-Optimizacion' -RestorePointType MODIFY_SETTINGS"
        )
        return TweakResult("restore_point", "ok" if ok else "error", "Creado" if ok else "No se pudo crear")

    def _tweak_telemetry(self, _o) -> TweakResult:
        backup = {
            "DiagTrack": self.query_powershell("(Get-Service DiagTrack).StartType"),
            "dmwappush": self.query_powershell("(Get-Service dmwappushservice).StartType"),
        }
        self.execute_powershell("Stop-Service -Name DiagTrack -Force -ErrorAction SilentlyContinue")
        self.execute_powershell("Set-Service -Name DiagTrack -StartupType Disabled")
        self.execute_powershell("Stop-Service -Name dmwappushservice -Force -ErrorAction SilentlyContinue")
        self.execute_powershell("Set-Service -Name dmwappushservice -StartupType Disabled")
        self.execute_powershell(
            "Disable-ScheduledTask -TaskPath '\\Microsoft\\Windows\\Customer Experience Improvement Program\\' "
            "-TaskName 'Consolidator' -ErrorAction SilentlyContinue"
        )
        ok = self._verify_service_disabled("DiagTrack")
        if ok:
            self._mark_applied("telemetry", backup)
        return TweakResult("telemetry", "ok" if ok else "error", "Verificado" if ok else "Servicio no deshabilitado")

    def _tweak_telemetry_extra(self, _o) -> TweakResult:
        services = ["dmwappushservice", "WerSvc", "PcaSvc"]
        backup = {s: self.query_powershell(f"(Get-Service {s} -ErrorAction SilentlyContinue).StartType") for s in services}
        for s in services:
            self.execute_powershell(f"Stop-Service -Name {s} -Force -ErrorAction SilentlyContinue")
            self.execute_powershell(f"Set-Service -Name {s} -StartupType Disabled -ErrorAction SilentlyContinue")
        self._mark_applied("telemetry_extra", backup)
        return TweakResult("telemetry_extra", "ok", "Servicios de telemetría extra ajustados")

    def _tweak_power_plan(self, _o) -> TweakResult:
        self.execute_powershell("powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>$null")
        ok, _ = self.execute_powershell(
            "$plan = Get-WmiObject -Class Win32_PowerPlan -Namespace root\\cimv2\\power "
            "| Where-Object {$_.ElementName -like '*Ultimate*'}; "
            "if ($plan) { powercfg -setactive $($plan.InstanceID.Split('\\')[1]); 'OK' }"
        )
        self._mark_applied("power_plan", {"note": "balanced_guid"})
        return TweakResult("power_plan", "ok" if ok else "error")

    def _tweak_power_fine(self, _o) -> TweakResult:
        backup = {}
        cmds = [
            "powercfg -setacvalueindex SCHEME_CURRENT SUB_DISK DISKIDLE 0",
            "powercfg -setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0",
            "powercfg -setactive SCHEME_CURRENT",
        ]
        for c in cmds:
            ok, _ = self.execute_powershell(c)
            if not ok:
                return TweakResult("power_fine", "error", "powercfg falló")
        self._mark_applied("power_fine", backup)
        return TweakResult("power_fine", "ok", "Disco timeout y USB suspend ajustados")

    def _tweak_temp(self, _o) -> TweakResult:
        paths = [
            "Remove-Item -Path $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue",
            "Remove-Item -Path 'C:\\Windows\\Temp\\*' -Recurse -Force -ErrorAction SilentlyContinue",
            "Remove-Item -Path 'C:\\Windows\\Prefetch\\*' -Recurse -Force -ErrorAction SilentlyContinue",
            "Remove-Item -Path 'C:\\Windows\\SoftwareDistribution\\Download\\*' -Recurse -Force -ErrorAction SilentlyContinue",
            "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
        ]
        for p in paths:
            self.execute_powershell(p)
        return TweakResult("temp", "ok", "Temp, Prefetch, WU cache y papelera limpiados")

    def _tweak_visual_effects(self, _o) -> TweakResult:
        backup = {
            "VisualFXSetting": self.query_powershell(
                "(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects' "
                "-Name VisualFXSetting -ErrorAction SilentlyContinue).VisualFXSetting"
            ),
            "EnableTransparency": self.query_powershell(
                "(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' "
                "-Name EnableTransparency -ErrorAction SilentlyContinue).EnableTransparency"
            ),
        }
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects' "
            "-Name 'VisualFXSetting' -Value 2 -Type DWord; "
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize' "
            "-Name 'EnableTransparency' -Value 0 -Type DWord; "
            "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop\\WindowMetrics' -Name 'MinAnimate' -Value '0'"
        )
        self._mark_applied("visual_effects", backup)
        return TweakResult("visual_effects", "ok")

    def _tweak_disk_optimize(self, _o) -> TweakResult:
        script = (
            "$ok = $true; "
            "Get-Volume | Where-Object {$_.DriveLetter} | ForEach-Object { "
            "  $dl = $_.DriveLetter; "
            "  $disk = Get-PhysicalDisk | Where-Object {$_.DeviceID -eq $_.DeviceID} | Select-Object -First 1; "
            "  $media = $disk.MediaType; "
            "  if ($media -eq 4 -or $media -eq 'SSD') { Optimize-Volume -DriveLetter $dl -ReTrim -ErrorAction SilentlyContinue } "
            "  else { defrag $dl`: /O /U | Out-Null } "
            "}; Write-Output 'done'"
        )
        ok, _ = self.execute_powershell(script)
        return TweakResult("disk_optimize", "ok" if ok else "error", "TRIM/defrag según tipo de disco")

    def _tweak_standby_ram(self, _o) -> TweakResult:
        ok, out = self.execute_powershell(
            "$sig = @'\n"
            "[DllImport(\"kernel32.dll\", SetLastError=true)]\n"
            "public static extern bool SetSystemFileCacheSize(IntPtr min, IntPtr max, int flags);\n"
            "'@; "
            "Add-Type -MemberDefinition $sig -Name Cache -Namespace Win32; "
            "[Win32.Cache]::SetSystemFileCacheSize([IntPtr](-1), [IntPtr](-1), 0) | Out-Null; "
            "[System.GC]::Collect(); "
            "$os = Get-CimInstance Win32_OperatingSystem; "
            "$free = [math]::Round($os.FreePhysicalMemory/1KB,1); "
            "Write-Output \"OK FreeMB=$free\""
        )
        if ok and "OK" in out:
            return TweakResult("standby_ram", "ok", out.replace("OK ", ""))
        return TweakResult("standby_ram", "error", out[:100] if out else "No se pudo liberar caché")

    def _tweak_gaming(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' -Name 'GameDVR_Enabled' -Value 0; "
            "Set-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' -Name 'GameDVR_FSEBehaviorMode' -Value 2; "
            "New-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\GameDVR' "
            "-Name 'AppCaptureEnabled' -Value 0 -PropertyType DWord -Force | Out-Null"
        )
        self._mark_applied("gaming", {})
        return TweakResult("gaming", "ok")

    def _tweak_game_mode(self, _o) -> TweakResult:
        self.execute_powershell(
            "$p = 'HKCU:\\Software\\Microsoft\\GameBar'; "
            "if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }; "
            "Set-ItemProperty -Path $p -Name 'AutoGameModeEnabled' -Value 1 -Type DWord"
        )
        self._mark_applied("game_mode", {})
        return TweakResult("game_mode", "ok")

    def _tweak_hags(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers' "
            "-Name 'HwSchMode' -Value 2 -Type DWord"
        )
        self._mark_applied("hags", {})
        return TweakResult("hags", "ok", "Requiere reinicio")

    def _tweak_mmcss(self, _o) -> TweakResult:
        self.execute_powershell(
            "$p = 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Multimedia\\SystemProfile'; "
            "Set-ItemProperty -Path $p -Name 'SystemResponsiveness' -Value 0 -Type DWord; "
            "$gp = $p + '\\Tasks\\Games'; "
            "if (-not (Test-Path $gp)) { New-Item -Path $gp -Force | Out-Null }; "
            "Set-ItemProperty -Path $gp -Name 'GPU Priority' -Value 8 -Type DWord"
        )
        self._mark_applied("mmcss", {})
        return TweakResult("mmcss", "ok")

    def _tweak_mouse_precision(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Mouse' -Name 'MouseSpeed' -Value '0'; "
            "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Mouse' -Name 'MouseThreshold1' -Value '0'; "
            "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Mouse' -Name 'MouseThreshold2' -Value '0'"
        )
        self._mark_applied("mouse_precision", {})
        return TweakResult("mouse_precision", "ok")

    def _tweak_vbs(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path "
            "'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\DeviceGuard\\Scenarios\\HypervisorEnforcedCodeIntegrity' "
            "-Name 'Enabled' -Value 0 -Type DWord"
        )
        self.execute_powershell("bcdedit /set hypervisorlaunchtype off")
        return TweakResult("vbs", "ok", "Requiere reinicio")

    def _tweak_core_parking(self, _o) -> TweakResult:
        ok, _ = self.execute_powershell(
            "powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR CPMINCORES 100; "
            "powercfg -setacvalueindex SCHEME_CURRENT SUB_PROCESSOR CPMAXCORES 100; "
            "powercfg -setactive SCHEME_CURRENT"
        )
        if ok:
            self._mark_applied("core_parking", {})
        return TweakResult("core_parking", "ok" if ok else "error")

    def _tweak_windowed_opt(self, _o) -> TweakResult:
        self.execute_powershell(
            "reg add 'HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences' "
            "/v DirectXUserGlobalSettings /t REG_SZ /d 'SwapEffectUpgradeEnable=1;' /f"
        )
        self._mark_applied("windowed_opt", {})
        return TweakResult("windowed_opt", "ok")

    def _tweak_auto_maintenance(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path "
            "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Schedule\\Maintenance' "
            "-Name 'MaintenanceDisabled' -Value 1 -Type DWord"
        )
        self._mark_applied("auto_maintenance", {})
        return TweakResult("auto_maintenance", "ok")

    def _tweak_power_throttling(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\PowerThrottling' "
            "-Name 'PowerThrottlingOff' -Value 1 -Type DWord"
        )
        self._mark_applied("power_throttling", {})
        return TweakResult("power_throttling", "ok")

    def _tweak_delivery_opt(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\DeliveryOptimization' "
            "-Name 'DODownloadMode' -Value 0 -Type DWord"
        )
        self._mark_applied("delivery_opt", {})
        return TweakResult("delivery_opt", "ok")

    def _tweak_network(self, _o) -> TweakResult:
        ok1, _ = self.execute_powershell("ipconfig /flushdns")
        ok2, _ = self.execute_powershell("netsh winsock reset")
        return TweakResult("network", "ok" if (ok1 or ok2) else "error")

    def _tweak_dns_custom(self, options: dict) -> TweakResult:
        use_dhcp = options.get("dns_dhcp", False)
        if use_dhcp:
            return self._revert_dns_dhcp()

        backup = self._capture_dns_backup()
        self.execute_powershell("ipconfig /flushdns")
        ok, out = self.execute_powershell(
            "$adapter = Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1; "
            "if ($adapter) { "
            "  Set-DnsClientServerAddress -InterfaceIndex $adapter.ifIndex "
            "    -ServerAddresses @('8.8.8.8','8.8.4.4','1.1.1.1','1.0.0.1'); 'OK' "
            "} else { 'NO_ADAPTER' }"
        )
        if ok and "OK" in out:
            verify = self.query_powershell(
                "$a = Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1; "
                "(Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4).ServerAddresses -join ','"
            )
            if "8.8.8.8" in verify:
                self._mark_applied("dns_custom", backup)
                return TweakResult("dns_custom", "ok", f"DNS aplicado ({verify})")
        return TweakResult("dns_custom", "error", out or "No se pudo verificar DNS")

    def _revert_dns_dhcp(self) -> TweakResult:
        backup = self.get_tweak_backup("dns_custom")
        idx = backup.get("ifIndex")
        if idx:
            ok, _ = self.execute_powershell(
                f"Set-DnsClientServerAddress -InterfaceIndex {idx} -ResetServerAddresses"
            )
        else:
            ok, _ = self.execute_powershell(
                "$a = Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1; "
                "Set-DnsClientServerAddress -InterfaceIndex $a.ifIndex -ResetServerAddresses"
            )
        if ok:
            self._mark_reverted("dns_custom")
        return TweakResult("dns_custom", "ok" if ok else "error", "DNS restaurado a DHCP")

    def _tweak_services(self, _o) -> TweakResult:
        backup = {
            "SysMain": self.query_powershell("(Get-Service SysMain).StartType"),
            "WSearch": self.query_powershell("(Get-Service WSearch).StartType"),
        }
        self.execute_powershell("Stop-Service -Name SysMain -Force -ErrorAction SilentlyContinue")
        self.execute_powershell("Set-Service -Name SysMain -StartupType Disabled")
        self.execute_powershell("Stop-Service -Name WSearch -Force -ErrorAction SilentlyContinue")
        self.execute_powershell("Set-Service -Name WSearch -StartupType Disabled")
        ok = self._verify_service_disabled("SysMain")
        if ok:
            self._mark_applied("services", backup)
        return TweakResult("services", "ok" if ok else "error")

    def _tweak_startup(self, _o) -> TweakResult:
        count = self.query_powershell(
            "(Get-CimInstance Win32_StartupCommand | Where-Object { $_.Location -notlike '*Microsoft*' }).Count"
        )
        self.execute_powershell(
            "Get-ScheduledTask | Where-Object {"
            " $_.TaskPath -eq '\\' -and $_.State -eq 'Ready' -and $_.Author -notlike '*Microsoft*'"
            " } | Disable-ScheduledTask -ErrorAction SilentlyContinue"
        )
        self.execute_powershell(
            "Get-CimInstance Win32_StartupCommand | Where-Object { $_.Location -notlike '*Microsoft*' } | "
            "ForEach-Object { $_.Name } | Out-File $env:TEMP\\resetx_startup_backup.txt"
        )
        self._mark_applied("startup", {"count_before": count})
        return TweakResult("startup", "ok", f"Tareas de inicio de terceros deshabilitadas ({count} detectadas)")

    def _tweak_fast_startup(self, _o) -> TweakResult:
        backup = {
            "SerializeTimeout": self.query_powershell(
                "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize' "
                "-Name StartupDelayInMSec -ErrorAction SilentlyContinue).StartupDelayInMSec"
            ),
        }
        self.execute_powershell(
            "New-Item -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize' -Force | Out-Null; "
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize' "
            "-Name 'StartupDelayInMSec' -Value 0 -Type DWord"
        )
        self._mark_applied("fast_startup", backup)
        return TweakResult("fast_startup", "ok", "Delay de arranque eliminado")

    def _tweak_tips_suggestions(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager' "
            "-Name 'SubscribedContent-338388Enabled' -Value 0 -Type DWord; "
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager' "
            "-Name 'SoftLandingEnabled' -Value 0 -Type DWord; "
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager' "
            "-Name 'SystemPaneSuggestionsEnabled' -Value 0 -Type DWord"
        )
        self._mark_applied("tips_suggestions", {})
        return TweakResult("tips_suggestions", "ok", "Sugerencias y tips desactivados")

    def _tweak_hibernate_off(self, _o) -> TweakResult:
        ok, out = self.execute_powershell("powercfg /hibernate off")
        if ok:
            self._mark_applied("hibernate_off", {"was_on": True})
        return TweakResult("hibernate_off", "ok" if ok else "error", out[:60] if out else "Hibernación desactivada")

    def _tweak_ntfs_optimize(self, _o) -> TweakResult:
        ok, out = self.execute_powershell("fsutil behavior set disablelastaccess 1")
        if ok:
            self._mark_applied("ntfs_optimize", {})
        return TweakResult("ntfs_optimize", "ok" if ok else "error", "Last access desactivado" if ok else out[:60])

    def _tweak_background_apps(self, _o) -> TweakResult:
        backup = self.query_powershell(
            "(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications' "
            "-Name GlobalUserDisabled -ErrorAction SilentlyContinue).GlobalUserDisabled"
        )
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications' "
            "-Name 'GlobalUserDisabled' -Value 1 -Type DWord"
        )
        self._mark_applied("background_apps", {"GlobalUserDisabled": backup})
        return TweakResult("background_apps", "ok", "Apps en segundo plano deshabilitadas")

    def _tweak_widgets_off(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced' "
            "-Name 'TaskbarDa' -Value 0 -Type DWord; "
            "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Dsh' "
            "-Name 'AllowNewsAndInterests' -Value 0 -Type DWord -ErrorAction SilentlyContinue"
        )
        self._mark_applied("widgets_off", {})
        return TweakResult("widgets_off", "ok", "Widgets desactivados (puede requerir reinicio)")

    def _tweak_fullscreen_opt(self, _o) -> TweakResult:
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' "
            "-Name 'GameDVR_DXGIHonorFSEWindowsCompatible' -Value 1 -Type DWord; "
            "Set-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' "
            "-Name 'GameDVR_FSEBehavior' -Value 2 -Type DWord; "
            "Set-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' "
            "-Name 'GameDVR_HonorUserFSEBehaviorMode' -Value 1 -Type DWord"
        )
        self._mark_applied("fullscreen_opt", {})
        return TweakResult("fullscreen_opt", "ok", "Optimizaciones fullscreen desactivadas")

    def _tweak_tcp_optimize(self, _o) -> TweakResult:
        cmds = [
            "netsh int tcp set global autotuninglevel=normal",
            "netsh int tcp set global chimney=disabled",
            "netsh int tcp set global dca=enabled",
            "netsh int tcp set global netdma=enabled",
            "netsh int tcp set global rss=enabled",
        ]
        ok_any = False
        for c in cmds:
            ok, _ = self.execute_powershell(c)
            ok_any = ok_any or ok
        self.execute_powershell(
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters' "
            "-Name 'TcpAckFrequency' -Value 1 -Type DWord; "
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters' "
            "-Name 'TCPNoDelay' -Value 1 -Type DWord"
        )
        if ok_any:
            self._mark_applied("tcp_optimize", {})
        return TweakResult("tcp_optimize", "ok" if ok_any else "error", "TCP ajustado para baja latencia")

    def _revert_tweak(self, tweak_id: str) -> TweakResult:
        self._status(tweak_id, "running")
        backup = self.get_tweak_backup(tweak_id)
        try:
            if tweak_id == "dns_custom":
                return self._revert_dns_dhcp()
            if tweak_id == "telemetry":
                for svc, st in backup.items():
                    if st:
                        self.execute_powershell(f"Set-Service -Name {svc} -StartupType {st}")
                self.execute_powershell("Start-Service -Name DiagTrack -ErrorAction SilentlyContinue")
            elif tweak_id == "telemetry_extra":
                for svc, st in backup.items():
                    if st:
                        self.execute_powershell(f"Set-Service -Name {svc} -StartupType {st} -ErrorAction SilentlyContinue")
            elif tweak_id == "power_plan":
                self.execute_powershell("powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e")
            elif tweak_id == "visual_effects":
                if backup.get("VisualFXSetting"):
                    self.execute_powershell(
                        f"Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects' "
                        f"-Name VisualFXSetting -Value {backup['VisualFXSetting']} -Type DWord"
                    )
            elif tweak_id == "services":
                self.execute_powershell("Set-Service -Name SysMain -StartupType Automatic")
                self.execute_powershell("Set-Service -Name WSearch -StartupType Automatic")
            elif tweak_id == "gaming":
                self.execute_powershell(
                    "Set-ItemProperty -Path 'HKCU:\\System\\GameConfigStore' -Name 'GameDVR_Enabled' -Value 1"
                )
            elif tweak_id == "game_mode":
                self.execute_powershell(
                    "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\GameBar' -Name 'AutoGameModeEnabled' -Value 0"
                )
            elif tweak_id == "hags":
                self.execute_powershell(
                    "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\GraphicsDrivers' "
                    "-Name 'HwSchMode' -Value 1 -Type DWord"
                )
            elif tweak_id == "fast_startup":
                val = backup.get("SerializeTimeout")
                if val:
                    self.execute_powershell(
                        f"Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize' "
                        f"-Name StartupDelayInMSec -Value {val} -Type DWord"
                    )
            elif tweak_id == "hibernate_off":
                self.execute_powershell("powercfg /hibernate on")
            elif tweak_id == "ntfs_optimize":
                self.execute_powershell("fsutil behavior set disablelastaccess 0")
            elif tweak_id == "background_apps":
                val = backup.get("GlobalUserDisabled", 0)
                self.execute_powershell(
                    f"Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\BackgroundAccessApplications' "
                    f"-Name GlobalUserDisabled -Value {val or 0} -Type DWord"
                )
            elif tweak_id == "widgets_off":
                self.execute_powershell(
                    "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced' "
                    "-Name TaskbarDa -Value 1 -Type DWord"
                )
            elif tweak_id == "tcp_optimize":
                self.execute_powershell(
                    "Remove-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters' "
                    "-Name TcpAckFrequency -ErrorAction SilentlyContinue; "
                    "Remove-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters' "
                    "-Name TCPNoDelay -ErrorAction SilentlyContinue"
                )
            else:
                self.log(f" [WARN] Revert genérico para {tweak_id}")
            self._mark_reverted(tweak_id)
            return TweakResult(tweak_id, "ok", "Revertido")
        except Exception as e:
            return TweakResult(tweak_id, "error", str(e))

    def optimize_all(self, options: dict):
        def worker():
            selected = [t for t in TWEAK_ORDER if options.get(t)]
            total = len(selected)
            done = 0
            results: list[TweakResult] = []
            try:
                if not self.is_admin() and any(self._needs_admin(t) for t in selected):
                    self.log("[WARN] Algunos tweaks requieren ejecutar ResetX como administrador.")
                self.log("[+] Iniciando optimización…")
                for tweak_id in selected:
                    label = TWEAK_META.get(tweak_id, {}).get("label", tweak_id)
                    if self.on_progress:
                        self.on_progress(done, total, tweak_id, label)
                    result = self._apply_tweak(tweak_id, options)
                    self._result(result)
                    results.append(result)
                    done += 1
                    if self.on_progress:
                        self.on_progress(done, total, tweak_id, label)
                ok_count = sum(1 for r in results if r.status == "ok")
                self.log(f"[OK] Completado: {ok_count}/{total} tweaks exitosos.")
                self.log("    *Reinicia el sistema para aplicar todos los cambios.*")
            except Exception as e:
                self.log(f"[ERROR] Proceso interrumpido: {e}")
            finally:
                if self.on_progress:
                    self.on_progress(total, total, "", "")
                if self.on_done:
                    self.on_done(results)
        threading.Thread(target=worker, daemon=True).start()

    def revert_tweaks(self, tweak_ids: list[str]):
        def worker():
            total = len(tweak_ids)
            done = 0
            results: list[TweakResult] = []
            try:
                self.log("[+] Revirtiendo tweaks…")
                for tweak_id in tweak_ids:
                    if tweak_id not in REVERTABLE:
                        r = TweakResult(tweak_id, "skipped", "No reversible")
                        self._result(r)
                        results.append(r)
                    else:
                        label = TWEAK_META.get(tweak_id, {}).get("label", tweak_id)
                        if self.on_progress:
                            self.on_progress(done, total, tweak_id, label)
                        r = self._revert_tweak(tweak_id)
                        self._result(r)
                        results.append(r)
                    done += 1
                    if self.on_progress:
                        self.on_progress(done, total, tweak_id, "")
                self.log("[OK] Reversión completada.")
            except Exception as e:
                self.log(f"[ERROR] Reversión interrumpida: {e}")
            finally:
                if self.on_progress:
                    self.on_progress(total, total, "", "")
                if self.on_done:
                    self.on_done(results)
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def count_available_tweaks() -> int:
        return len(TWEAK_ORDER)

    @staticmethod
    def get_label(tweak_id: str) -> str:
        return TWEAK_META.get(tweak_id, {}).get("label", tweak_id)
