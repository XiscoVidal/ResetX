"""Audita el catálogo contra paquetes beta/problemáticos en winget."""
import json
import re
import subprocess
import sys

BETA_RE = re.compile(r"(?i)(beta|preview|insider|canary|nightly|alpha|experimental|unstable)")
ROOT = __file__.replace("\\", "/").rsplit("/", 2)[0]


def winget_show(app_id: str) -> tuple[int, str]:
    r = subprocess.run(
        ["winget", "show", "--id", app_id, "-e", "--accept-source-agreements"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    db = json.load(open(f"{ROOT}/data/apps_database.json", encoding="utf-8"))
    issues = []
    for cat in db["categorias"]:
        for app in cat["apps"]:
            aid = app["id"]
            if "." not in aid:
                continue
            code, out = winget_show(aid)
            if code != 0:
                issues.append({"id": aid, "name": app["nombre"], "issue": "NOT_FOUND"})
                continue
            ver_m = re.search(r"^Version:\s*(.+)$", out, re.M)
            ver = ver_m.group(1).strip() if ver_m else "?"
            url_m = re.search(r"Installer Url:\s*(.+)$", out, re.M)
            url = url_m.group(1).strip() if url_m else ""
            name_m = re.search(r"^Found (.+?) \[", out, re.M)
            name = name_m.group(1) if name_m else ""

            if BETA_RE.search(ver):
                issues.append({"id": aid, "name": app["nombre"], "issue": "BETA_VERSION", "detail": ver})
            if BETA_RE.search(name):
                issues.append({"id": aid, "name": app["nombre"], "issue": "BETA_NAME", "detail": name})
            if BETA_RE.search(url):
                issues.append({"id": aid, "name": app["nombre"], "issue": "BETA_URL", "detail": url[:100]})
            if aid.lower() == "overwolf.curseforge":
                issues.append({"id": aid, "name": app["nombre"], "issue": "CURSEFORGE_OVERWOLF_BETA", "detail": url})

    print(json.dumps(issues, indent=2, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
