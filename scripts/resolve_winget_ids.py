"""Resuelve IDs winget correctos para el catálogo."""
import json
import re
import subprocess
import sys

ROOT = __file__.replace("\\", "/").rsplit("/", 2)[0]
BROKEN = [
    "RiotGames.RiotClient", "Zed.Zed", "Blockbench.Blockbench", "Bitsum.ProcessLasso",
    "Nvidia.NvidiaApp", "AMD.Adrenalin", "Clonezilla.Clonezilla", "TranslucentTB.TranslucentTB",
    "Microsoft.WindowsStore", "GameSir.Nexus", "OCCT.OCPT", "OPAutoClicker.AutoClicker",
    "DualMonitorTools.DualMonitorTools", "Dev47Apps.DroidCam", "Cisco.PacketTracer",
    "RustDesk.RustDesk", "FileZilla.FileZilla", "Pi-hole.Pi-hole", "SG.TCPOptimizer",
    "ExitLag.ExitLag", "Bitvise.SSHClient", "Azahar.Emulator", "BlueStacks.BlueStacks",
    "ARKServerManager.ASM", "RustServerManager.RSM", "RustServerTool.RST", "Medal.Medal",
    "Streamlabs.StreamlabsDesktop", "Faceit.Faceit", "Ryochan7.DS4Windows", "CheatEngine.CheatEngine",
]


def search(query: str) -> list[str]:
    r = subprocess.run(
        ["winget", "search", query, "--accept-source-agreements", "--source", "winget"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    ids = []
    for line in (r.stdout or "").splitlines():
        m = re.match(r"^[^\s].*?\s+([A-Za-z0-9][\w\.+-]*)\s+\S", line)
        if m and "." in m.group(1):
            ids.append(m.group(1))
    return ids[:5]


def show_id(app_id: str) -> bool:
    r = subprocess.run(
        ["winget", "show", "--id", app_id, "-e", "--accept-source-agreements", "--source", "winget"],
        capture_output=True, timeout=25,
    )
    return r.returncode == 0


if __name__ == "__main__":
    db = json.load(open(f"{ROOT}/data/apps_database.json", encoding="utf-8"))
    names = {a["id"]: a["nombre"] for c in db["categorias"] for a in c["apps"]}
    for old in BROKEN:
        if old not in names:
            old_ids = [k for k, v in names.items() if v and old.split(".")[-1].lower() in k.lower()]
        name = names.get(old, old.split(".")[-1])
        q = name.split()[0] if name else old.split(".")[-1]
        hits = search(q)
        valid = [i for i in hits if show_id(i)]
        print(f"{old} ({name}) -> {valid[:3]}")
