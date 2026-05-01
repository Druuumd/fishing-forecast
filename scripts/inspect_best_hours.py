"""Quick inspection of best_hours field in live forecast."""
import json
import urllib.request

with urllib.request.urlopen(
    "https://kvh-forecast.ru/v1/forecast?species=pike", timeout=15
) as resp:
    r = json.load(resp)

for d in r["days"][:3]:
    print(f"\n{d['date']}  moon_phase={d['moon_phase']:.2f}")
    print(f"  sunrise={d.get('sunrise')}  sunset={d.get('sunset')}")
    bh = d.get("best_hours", [])
    print(f"  best_hours: {len(bh)}")
    for w in bh:
        print(f"    {w['kind']:<14} {w['label']:<40} {w['start']}  →  {w['end']}")
