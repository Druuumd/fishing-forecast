"""Quick inspection of species-spawn factor + warnings on the live API."""
import json
import urllib.request

print("=== Pike day-0 score factors ===")
with urllib.request.urlopen(
    "https://kvh-forecast.ru/v1/forecast?species=pike", timeout=15
) as resp:
    r = json.load(resp)
d = r["days"][0]
print(f"Tw (default zone): {d['water_temp_c']}°C  date: {d['date']}")
for f in d["factors"]:
    if f["name"] in ("species_spawn", "season", "water_temp"):
        print(f"  {f['contribution']:+.3f}  {f['name']:<18} {f.get('detail') or ''}")

print("\n=== Spawning warnings active ===")
with urllib.request.urlopen("https://kvh-forecast.ru/v1/warnings", timeout=15) as resp:
    r = json.load(resp)
spawn = [w for w in r["warnings"] if "_spawning" in w["code"] or w["code"] == "spawning_ban"]
for w in spawn:
    print(f"  {w['severity']:>6}  {w['code']:<22} {w['title']}")
    print(f"          {w['body'][:100]}…")

print("\n=== Per-species spawn factor (across pike/perch/bream) ===")
for sp in ("pike", "perch", "bream"):
    with urllib.request.urlopen(
        f"https://kvh-forecast.ru/v1/forecast?species={sp}", timeout=15
    ) as resp:
        r = json.load(resp)
    d = r["days"][0]
    spawn_factor = next((f for f in d["factors"] if f["name"] == "species_spawn"), None)
    if spawn_factor:
        print(f"  {sp:<6} score={d['score']:.2f}  spawn={spawn_factor['contribution']:+.3f} ({spawn_factor['detail']})")
    else:
        print(f"  {sp:<6} score={d['score']:.2f}  spawn=none")
