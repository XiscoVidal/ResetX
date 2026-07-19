"""Corrige IDs winget rotos y marca apps no disponibles."""
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
    "RockstarGames.Launcher": ("RockstarGames.Launcher", None),  # keep id, tune install
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
    "Microsoft.WindowsStore", "GameSir.Nexus", "DualMonitorTools.DualMonitorTools",
    "Cisco.PacketTracer", "RustDesk.RustDesk", "FileZilla.FileZilla",
    "Pi-hole.Pi-hole", "SG.TCPOptimizer", "ExitLag.ExitLag",
    "ARKServerManager.ASM", "RustServerManager.RSM", "RustServerTool.RST",
    "Ryochan7.DS4Windows", "CheatEngine.CheatEngine",
}


def main():
    db = json.loads(DB.read_text(encoding="utf-8"))
    for cat in db["categorias"]:
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
                app["desc"] = (app.get("desc", "") + " (no disponible en winget)").strip()
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Catalog updated:", len(FIXES), "fixes,", len(UNAVAILABLE), "unavailable")


if __name__ == "__main__":
    main()
