import os
import psutil
import time
import subprocess
import threading
import re

class SystemMetrics:
    _hardware_cache = None
    _is_fetching = False

    _last_time = time.time()
    _last_net = psutil.net_io_counters()
    _last_disk = psutil.disk_io_counters()
    _gpu_cache = {"percent": 0, "power": 0, "temp": 0, "clock_core": 0, "clock_mem": 0, "has_data": False}
    _cpu_perf_cache = 100
    _lhm_computer = None

    _telemetry_cache = None
    _telemetry_cache_time = 0
    _telemetry_lock = threading.Lock()
    _TELEMETRY_TTL = 1.5

    _bg_worker_started = False
    _bg_worker_lock = threading.Lock()

    _power_plans_cache = None
    _power_plans_ready = threading.Event()

    @staticmethod
    def _clean_cpu_name(raw_name):
        name = raw_name
        name = re.sub(r"\s*\(R\)\s*", " ", name)
        name = re.sub(r"\s*\(TM\)\s*", " ", name)
        name = re.sub(r"\s*CPU\s*@.*", "", name)
        name = re.sub(r"^\d{1,2}th Gen\s+", "", name)
        name = name.replace("Intel(R) Core(TM) ", "").replace("AMD ", "").replace("Processor", "").strip()
        return name.strip()

    @staticmethod
    def _ensure_bg_worker():
        with SystemMetrics._bg_worker_lock:
            if SystemMetrics._bg_worker_started:
                return
            SystemMetrics._bg_worker_started = True
            threading.Thread(target=SystemMetrics._bg_worker_loop, daemon=True).start()

    @staticmethod
    def _bg_worker_loop():
        while True:
            try:
                SystemMetrics._fetch_gpu_dynamic()
                SystemMetrics._fetch_cpu_perf_dynamic()
            except Exception:
                pass
            time.sleep(2.0)

    @staticmethod
    def _init_lhm():
        if SystemMetrics._lhm_computer is not None:
            return
        try:
            import clr
            from backend.utils import get_base_path
            dll_path = os.path.join(get_base_path(), "backend", "LHM", "LibreHardwareMonitorLib.dll")
            if not os.path.exists(dll_path):
                return
            clr.AddReference(dll_path)
            from LibreHardwareMonitor import Hardware
            computer = Hardware.Computer()
            computer.IsCpuEnabled = True
            computer.IsGpuEnabled = True
            computer.Open()
            SystemMetrics._lhm_computer = computer
        except Exception:
            pass

    @staticmethod
    def _read_lhm_sensors():
        cpu_temp = 0
        cpu_power = None
        gpu_temp = 0
        gpu_power = 0
        try:
            SystemMetrics._init_lhm()
            if not SystemMetrics._lhm_computer:
                return cpu_temp, cpu_power, gpu_temp, gpu_power
            for hw in SystemMetrics._lhm_computer.Hardware:
                hw.Update()
                hw_type = str(hw.HardwareType)
                if hw_type == "Cpu":
                    for sensor in hw.Sensors:
                        sname = str(sensor.Name)
                        stype = str(sensor.SensorType)
                        if stype == "Temperature" and sensor.Value is not None:
                            if "Package" in sname or "Core" in sname:
                                cpu_temp = max(cpu_temp, round(sensor.Value))
                        if stype == "Power" and "Package" in sname and sensor.Value is not None:
                            cpu_power = round(sensor.Value, 1)
                elif "Gpu" in hw_type:
                    for sensor in hw.Sensors:
                        stype = str(sensor.SensorType)
                        sname = str(sensor.Name)
                        if stype == "Temperature" and "Core" in sname and sensor.Value is not None:
                            gpu_temp = max(gpu_temp, round(sensor.Value))
                        if stype == "Power" and sensor.Value is not None and "Board" not in sname:
                            gpu_power = max(gpu_power, float(sensor.Value))
        except Exception:
            pass
        return cpu_temp, cpu_power, gpu_temp, gpu_power

    @staticmethod
    def get_hardware_specs():
        if SystemMetrics._hardware_cache is not None:
            return SystemMetrics._hardware_cache

        if not SystemMetrics._is_fetching:
            SystemMetrics._is_fetching = True
            SystemMetrics._hardware_cache = {
                "CPU": "Cargando...",
                "GPU": "Cargando...",
                "Driver": "Cargando...",
                "RAM_GB": "Cargando...",
                "RAM_MHz": "Cargando...",
                "RAM_Type": "RAM",
                "Disks": [],
            }
            threading.Thread(target=SystemMetrics._fetch_hardware_worker, daemon=True).start()

        return SystemMetrics._hardware_cache

    @staticmethod
    def _fetch_hardware_worker():
        try:
            cpu_raw = subprocess.check_output(
                'powershell -NoProfile -Command "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"',
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            ).strip()
            cpu = SystemMetrics._clean_cpu_name(cpu_raw)

            gpu = subprocess.check_output(
                'powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -notlike \'*Basic*\'} | Select-Object -First 1).Name"',
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            ).strip()
            try:
                pnp = subprocess.check_output(
                    'powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController | Select-Object -First 1).PNPDeviceID"',
                    shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                ).strip()
                match = re.search(r"SUBSYS_[0-9A-F]{4}([0-9A-F]{4})", pnp)
                brand = ""
                if match:
                    brands = {
                        "1043": "ASUS", "1462": "MSI", "1458": "Gigabyte", "3842": "EVGA",
                        "1DA2": "Sapphire", "148C": "PowerColor", "1682": "XFX", "1E90": "ASRock",
                        "10DE": "NVIDIA", "19DA": "Zotac", "10B0": "Gainward",
                    }
                    brand = brands.get(match.group(1).upper(), "")
            except Exception:
                brand = ""

            gpu = gpu.replace("NVIDIA GeForce ", "").replace("AMD Radeon ", "").strip()
            if brand and not gpu.startswith(brand):
                gpu = f"{brand} {gpu}"

            driver = subprocess.check_output(
                'powershell -NoProfile -Command "(Get-CimInstance Win32_VideoController | Select-Object -First 1).DriverVersion"',
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            ).strip()

            ram_speed = subprocess.check_output(
                'powershell -NoProfile -Command "(Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1).Speed"',
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            ).strip()
            ram_part = subprocess.check_output(
                'powershell -NoProfile -Command "(Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1).PartNumber"',
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            ).strip()

            try:
                smbios_type = int(subprocess.check_output(
                    'powershell -NoProfile -Command "(Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1).SMBIOSMemoryType"',
                    shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                ).strip())
                ram_type = "DDR4" if smbios_type in [26, 30] else "DDR5" if smbios_type in [34, 35] else "DDR"
            except Exception:
                ram_type = "DDR"

            speed_int = int(ram_speed) if ram_speed.isdigit() else 0
            xmp_str = ""
            if (ram_type == "DDR4" and speed_int > 2666) or (ram_type == "DDR5" and speed_int > 4800):
                xmp_str = " (XMP/EXPO)"

            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))

            disks = []
            try:
                ps_cmd = (
                    'powershell -NoProfile -Command "'
                    "Get-CimInstance Win32_DiskDrive | "
                    "ForEach-Object { $_.Model + '|' + [math]::Round($_.Size/1GB) }"
                    '"'
                )
                disk_raw = subprocess.check_output(ps_cmd, shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).strip()
                for line in disk_raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("|")
                    model = parts[0].strip() if parts else "Desconocido"
                    gb = parts[1].strip() if len(parts) > 1 else "?"
                    disks.append({"model": model, "gb": gb})
            except Exception:
                disks = [{"model": "Desconocido", "gb": "?"}]

            SystemMetrics._hardware_cache = {
                "CPU": cpu if cpu else "Desconocido",
                "GPU": gpu if gpu else "Desconocida",
                "Driver": driver if driver else "N/A",
                "RAM_GB": str(ram_gb),
                "RAM_MHz": ram_speed,
                "RAM_Type": f"{ram_part} - {ram_type} a {ram_speed} MHz{xmp_str}",
                "Disks": disks,
            }
        except Exception:
            SystemMetrics._hardware_cache = {
                "CPU": "Error leyendo CPU",
                "GPU": "Error leyendo GPU",
                "Driver": "N/A",
                "RAM_GB": "N/A",
                "RAM_MHz": "N/A",
                "RAM_Type": "RAM",
                "Disks": [{"model": "Error", "gb": "?"}],
            }
        finally:
            SystemMetrics._is_fetching = False

    @staticmethod
    def _fetch_gpu_dynamic():
        try:
            res = subprocess.check_output(
                "nvidia-smi --query-gpu=utilization.gpu,power.draw,temperature.gpu,clocks.gr,clocks.mem --format=csv,noheader,nounits",
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            parts = res.strip().split(",")
            if len(parts) >= 5:
                SystemMetrics._gpu_cache["percent"] = int(parts[0].strip())
                SystemMetrics._gpu_cache["power"] = float(parts[1].strip())
                SystemMetrics._gpu_cache["temp"] = int(parts[2].strip())
                SystemMetrics._gpu_cache["clock_core"] = int(parts[3].strip())
                SystemMetrics._gpu_cache["clock_mem"] = int(parts[4].strip())
                SystemMetrics._gpu_cache["has_data"] = True
                return
        except Exception:
            pass

        try:
            ps = (
                'powershell -NoProfile -Command "'
                "$g = Get-CimInstance Win32_PerfFormattedData_Counters_GPUEngine -ErrorAction SilentlyContinue | "
                "Where-Object {$_.Name -like '*engtype_3D*'} | Select-Object -First 1; "
                "if ($g) { $g.UtilizationPercentage } else { 0 }"
                '"'
            )
            util = subprocess.check_output(ps, shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).strip()
            if util.isdigit() and int(util) > 0:
                SystemMetrics._gpu_cache["percent"] = int(util)
                SystemMetrics._gpu_cache["has_data"] = True
        except Exception:
            pass

        lhm_cpu, _, lhm_gpu_temp, lhm_gpu_pwr = SystemMetrics._read_lhm_sensors()
        if lhm_gpu_temp > 0:
            SystemMetrics._gpu_cache["temp"] = lhm_gpu_temp
            SystemMetrics._gpu_cache["has_data"] = True
        if lhm_gpu_pwr > 0:
            SystemMetrics._gpu_cache["power"] = lhm_gpu_pwr
            SystemMetrics._gpu_cache["has_data"] = True

    @staticmethod
    def _fetch_cpu_perf_dynamic():
        try:
            res = subprocess.check_output(
                'powershell -NoProfile -Command "(Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation | Where-Object Name -eq \'_Total\').PercentProcessorPerformance"',
                shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            val = res.strip()
            if val.isdigit():
                SystemMetrics._cpu_perf_cache = int(val)
        except Exception:
            pass

    @staticmethod
    def _compute_telemetry():
        now = time.time()
        dt = now - SystemMetrics._last_time
        if dt == 0:
            dt = 0.001

        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()

        net_dl = (net.bytes_recv - SystemMetrics._last_net.bytes_recv) / dt / (1024 * 1024)
        net_ul = (net.bytes_sent - SystemMetrics._last_net.bytes_sent) / dt / (1024 * 1024)
        disk_r = (disk.read_bytes - SystemMetrics._last_disk.read_bytes) / dt / (1024 * 1024)
        disk_w = (disk.write_bytes - SystemMetrics._last_disk.write_bytes) / dt / (1024 * 1024)

        freq_info = psutil.cpu_freq()
        base_ghz = freq_info.current / 1000 if freq_info else 3.0
        cpu_ghz = round(base_ghz * (SystemMetrics._cpu_perf_cache / 100.0), 2)

        cpu_temp, cpu_power_lhm, lhm_gpu_temp, lhm_gpu_pwr = SystemMetrics._read_lhm_sensors()

        if cpu_temp == 0:
            try:
                temp_res = subprocess.check_output(
                    'powershell -NoProfile -Command "(Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace root/wmi -ErrorAction SilentlyContinue | Select-Object -First 1).CurrentTemperature"',
                    shell=True, text=True, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                ).strip()
                if temp_res.isdigit():
                    cpu_temp = round((int(temp_res) / 10.0) - 273.15)
            except Exception:
                pass

        if cpu_temp == 0:
            try:
                temp_res = subprocess.check_output(
                    'powershell -NoProfile -Command "(Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation | Select-Object -First 1).Temperature"',
                    shell=True, text=True, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                ).strip()
                if temp_res.isdigit():
                    val = int(temp_res)
                    cpu_temp = round(val - 273.15) if val > 200 else val
            except Exception:
                pass

        cpu_pct = psutil.cpu_percent(interval=None)
        if cpu_temp <= 30 or cpu_temp > 110:
            ambient = 32
            cpu_temp = int(ambient + (cpu_pct * 0.65) + (cpu_ghz * 2.5))

        SystemMetrics._ensure_bg_worker()

        gpu_power = SystemMetrics._gpu_cache.get("power", 0) or lhm_gpu_pwr
        gpu_temp = SystemMetrics._gpu_cache.get("temp", 0) or lhm_gpu_temp
        gpu_core = SystemMetrics._gpu_cache.get("clock_core", 0)
        gpu_mem = SystemMetrics._gpu_cache.get("clock_mem", 0)
        has_gpu = SystemMetrics._gpu_cache.get("has_data", False)

        if cpu_power_lhm is not None:
            cpu_power_est = cpu_power_lhm
        else:
            cpu_power_est = 25.0 + (cpu_pct / 100.0) * 160.0

        total_sys_power = round(cpu_power_est + gpu_power + 30.0, 1)

        SystemMetrics._last_time = now
        SystemMetrics._last_net = net
        SystemMetrics._last_disk = disk

        return {
            "cpu_ghz": cpu_ghz,
            "cpu_temp_c": cpu_temp,
            "net_dl_mbs": round(max(0, net_dl), 1),
            "net_ul_mbs": round(max(0, net_ul), 1),
            "disk_read_mbs": round(max(0, disk_r), 1),
            "disk_write_mbs": round(max(0, disk_w), 1),
            "gpu_power_w": round(gpu_power, 1),
            "gpu_percent": SystemMetrics._gpu_cache.get("percent", 0),
            "gpu_temp_c": gpu_temp,
            "gpu_clock_core": gpu_core if has_gpu and gpu_core > 0 else None,
            "gpu_clock_mem": gpu_mem if has_gpu and gpu_mem > 0 else None,
            "total_power_w": total_sys_power,
        }

    @staticmethod
    def get_dynamic_telemetry():
        now = time.time()
        with SystemMetrics._telemetry_lock:
            if SystemMetrics._telemetry_cache and (now - SystemMetrics._telemetry_cache_time) < SystemMetrics._TELEMETRY_TTL:
                return SystemMetrics._telemetry_cache.copy()
        data = SystemMetrics._compute_telemetry()
        with SystemMetrics._telemetry_lock:
            SystemMetrics._telemetry_cache = data
            SystemMetrics._telemetry_cache_time = now
        return data.copy()

    @staticmethod
    def _fetch_power_plans_worker():
        try:
            out = subprocess.check_output("powercfg /L", shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            plans = {}
            active = None
            for line in out.splitlines():
                if "GUID" in line:
                    match = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", line)
                    if not match:
                        continue
                    guid = match.group(1)
                    name_start = line.find("(") + 1
                    name_end = line.find(")")
                    name = line[name_start:name_end]
                    if "ximo" in name.lower() and "rendimiento" in name.lower():
                        name = "Maximo rendimiento"
                    plans[name] = guid
                    if "*" in line:
                        active = name
            SystemMetrics._power_plans_cache = (plans, active)
        except Exception:
            SystemMetrics._power_plans_cache = ({"Equilibrado": ""}, "Equilibrado")
        finally:
            SystemMetrics._power_plans_ready.set()

    @staticmethod
    def get_power_plans():
        if SystemMetrics._power_plans_cache is None:
            threading.Thread(target=SystemMetrics._fetch_power_plans_worker, daemon=True).start()
            SystemMetrics._power_plans_ready.wait(timeout=3.0)
        if SystemMetrics._power_plans_cache is None:
            return {"Equilibrado": ""}, "Equilibrado"
        return SystemMetrics._power_plans_cache

    @staticmethod
    def set_power_plan(guid):
        if guid:
            try:
                subprocess.run(["powercfg", "/S", guid], creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                SystemMetrics._power_plans_cache = None
                SystemMetrics._power_plans_ready.clear()
            except Exception as e:
                print(f"Error changing power plan: {e}")

    @staticmethod
    def get_cpu_usage():
        return psutil.cpu_percent(interval=None)

    @staticmethod
    def get_ram_usage():
        mem = psutil.virtual_memory()
        return {
            "percent": mem.percent,
            "used_gb": round(mem.used / (1024 ** 3), 1),
            "total_gb": round(mem.total / (1024 ** 3), 1),
        }

    @staticmethod
    def get_disk_usage(drive="C:\\"):
        try:
            disk = psutil.disk_usage(drive)
        except Exception:
            disk = psutil.disk_usage("C:\\")
        return {
            "percent": disk.percent,
            "free_gb": round(disk.free / (1024 ** 3), 1),
            "total_gb": round(disk.total / (1024 ** 3), 1),
        }

    @staticmethod
    def get_all_drive_usage():
        """Uso por letra de unidad disponible."""
        usage = {}
        for part in psutil.disk_partitions():
            if "cdrom" in part.opts.lower() or not part.mountpoint:
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
                letter = part.mountpoint.rstrip("\\")
                usage[letter] = {
                    "percent": u.percent,
                    "used_gb": round((u.total - u.free) / (1024 ** 3), 1),
                    "total_gb": round(u.total / (1024 ** 3), 1),
                    "free_gb": round(u.free / (1024 ** 3), 1),
                }
            except Exception:
                pass
        return usage

    @staticmethod
    def get_uptime_hours():
        uptime_seconds = time.time() - psutil.boot_time()
        hours = uptime_seconds / 3600
        if hours < 24:
            return round(hours, 1), f"{int(hours)}h {int((uptime_seconds % 3600) / 60)}m"
        days = int(hours // 24)
        return round(hours, 1), f"{days}d {int(hours % 24)}h"

    @staticmethod
    def calculate_health_score():
        cpu = SystemMetrics.get_cpu_usage()
        ram = SystemMetrics.get_ram_usage()["percent"]
        disk = SystemMetrics.get_disk_usage()["percent"]
        live = SystemMetrics.get_dynamic_telemetry()
        cpu_temp = live.get("cpu_temp_c", 0)
        uptime_h, _ = SystemMetrics.get_uptime_hours()

        score = 100
        if cpu > 80:
            score -= 15
        elif cpu > 50:
            score -= 5
        if ram > 90:
            score -= 20
        elif ram > 70:
            score -= 10
        if disk > 90:
            score -= 15
        elif disk > 80:
            score -= 5

        if cpu_temp > 85:
            score -= 15
        elif cpu_temp > 75:
            score -= 8
        elif cpu_temp > 65:
            score -= 3

        if uptime_h > 168:
            score -= 10
        elif uptime_h > 72:
            score -= 5

        return max(0, min(100, score))
