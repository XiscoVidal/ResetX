import re
import requests

h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get("https://www.curseforge.com/download/app", headers=h, timeout=20)
print("status", r.status_code)
for m in re.findall(r"https?://[^\s\"'<>]+", r.text):
    if "curseforge" in m.lower() or m.endswith(".exe"):
        print(m[:150])
