"""Corrige IDs winget, marca apps no disponibles, añade enlaces de descarga y limpia el catálogo."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "apps_database.json"

# catalog_id -> (winget_id, source|None)
FIXES: dict[str, tuple[str, str | None]] = {
    "Bitsum.ProcessLasso": ("BitSum.ProcessLasso", None),
    "Blockbench.Blockbench": ("JannisX11.Blockbench", None),
    "TranslucentTB.TranslucentTB": ("CharlesMilette.TranslucentTB", None),
    "Dev47Apps.DroidCam": ("dev47apps.DroidCam", None),
    "OPAutoClicker.AutoClicker": ("OPAutoClicker.OPAutoClicker", None),
    "Bitvise.SSHClient": ("Bitvise.SSH.Client", None),
    "Azahar.Emulator": ("AzaharEmu.Azahar", None),
    "BlueStacks.BlueStacks": ("BlueStack.BlueStacks", None),
    "Medal.Medal": ("MedalB.V.Medal", None),
    "Streamlabs.StreamlabsDesktop": ("Streamlabs.Streamlabs", None),
    "Faceit.Faceit": ("FACEITLTD.FACEITClient", None),
    "OCCT.OCCT": ("OCBase.OCCT.Personal", None),
    "Zed.Zed": ("ZedIndustries.Zed", None),
    "Nvidia.NvidiaApp": ("XP8CLZL93F5Z4P", "msstore"),
    "RockstarGames.Launcher": ("RockstarGames.Launcher", None),
}

SILENT_OFF = {
    "RockstarGames.Launcher",
    "EpicGames.EpicGamesLauncher",
    "Valve.Steam",
    "ElectronicArts.EADesktop",
    "Blizzard.BattleNet",
}

UNAVAILABLE = {
    "RiotGames.RiotClient", "AMD.Adrenalin", "Clonezilla.Clonezilla",
    "GameSir.Nexus", "DualMonitorTools.DualMonitorTools",
    "Cisco.PacketTracer", "RustDesk.RustDesk", "FileZilla.FileZilla",
    "Pi-hole.Pi-hole", "SG.TCPOptimizer", "ExitLag.ExitLag",
    "Ryochan7.DS4Windows", "CheatEngine.CheatEngine",
}

REMOVE_FROM_CATALOG = {
    "Microsoft.WindowsStore",
    "ARKServerManager.ASM",
    "RustServerManager.RSM",
    "RustServerTool.RST",
}

# catalog_id -> (download_url|None, download_page)
DOWNLOADS: dict[str, tuple[str | None, str]] = {
    "RiotGames.RiotClient": (None, "https://www.riotgames.com/"),
    "AMD.Adrenalin": (None, "https://www.amd.com/en/support/download/drivers.html"),
    "Clonezilla.Clonezilla": (None, "https://clonezilla.org/downloads.php"),
    "RustDesk.RustDesk": (None, "https://rustdesk.com/download"),
    "FileZilla.FileZilla": (None, "https://filezilla-project.org/download.php?type=client"),
    "Ryochan7.DS4Windows": (None, "https://ds4-windows.com/"),
    "CheatEngine.CheatEngine": (None, "https://www.cheatengine.org/downloads.php"),
    "Cisco.PacketTracer": (None, "https://www.netacad.com/courses/packet-tracer"),
    "ExitLag.ExitLag": (None, "https://www.exitlag.com/download"),
    "GameSir.Nexus": (None, "https://www.gamesir.hk/pages/gamesir-app"),
    "DualMonitorTools.DualMonitorTools": (None, "https://dualmonitortool.sourceforge.net/download.html"),
    "Pi-hole.Pi-hole": (None, "https://pi-hole.net"),
    "SG.TCPOptimizer": (None, "https://www.speedguide.net/downloads.php"),
    "CurseForge.App": (
        "https://curseforge.overwolf.com/downloads/curseforge-latest-win64.exe",
        "https://www.curseforge.com/download/app",
    ),
}

CURSEFORGE_ENTRY = {
    "id": "CurseForge.App",
    "nombre": "CurseForge",
    "desc": "Cliente oficial de mods (descarga directa estable, sin beta Overwolf)",
    "size": "0.2 GB",
    "dominio": "curseforge.com",
    "rating": "⭐⭐⭐⭐⭐",
    "install_mode": "direct",
    "download_url": "https://curseforge.overwolf.com/downloads/curseforge-latest-win64.exe",
    "download_page": "https://www.curseforge.com/download/app",
}


def main():
    db = json.loads(DB.read_text(encoding="utf-8"))

    for cat in db["categorias"]:
        cat["apps"] = [a for a in cat["apps"] if a["id"] not in REMOVE_FROM_CATALOG]

        if cat["id"] == "gaming-tools":
            cat["apps"] = [a for a in cat["apps"] if a["id"] != "WowUp.CF"]
            if not any(a["id"] == "CurseForge.App" for a in cat["apps"]):
                cat["apps"].insert(0, dict(CURSEFORGE_ENTRY))

        for app in cat["apps"]:
            aid = app["id"]

            if aid in FIXES:
                wid, src = FIXES[aid]
                app["winget_id"] = wid
                if src:
                    app["source"] = src

            if aid in SILENT_OFF:
                app["install_silent"] = False

            if aid in UNAVAILABLE:
                app["hub_unavailable"] = True
                if "(no disponible en winget)" not in (app.get("desc") or ""):
                    app["desc"] = (app.get("desc", "") + " (no disponible en winget)").strip()

            if aid in DOWNLOADS:
                dl_url, dl_page = DOWNLOADS[aid]
                if dl_url:
                    app["download_url"] = dl_url
                elif "download_url" in app:
                    app.pop("download_url", None)
                if dl_page:
                    app["download_page"] = dl_page

            if app.get("hub_unavailable") and not app.get("download_page"):
                domain = app.get("dominio")
                if domain:
                    app["download_page"] = f"https://{domain}"

    db["categorias"] = [c for c in db["categorias"] if c["apps"]]

    DB.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total_apps = sum(len(c["apps"]) for c in db["categorias"])
    unavailable_count = sum(
        1 for c in db["categorias"] for a in c["apps"] if a.get("hub_unavailable")
    )
    removed = len(REMOVE_FROM_CATALOG)
    print(f"Catalog updated: {total_apps} apps, {len(FIXES)} ID fixes, "
          f"{unavailable_count} unavailable, {removed} removed, "
          f"{len(DOWNLOADS)} download links")


if __name__ == "__main__":
    main()
