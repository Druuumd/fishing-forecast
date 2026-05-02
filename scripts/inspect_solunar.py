"""Inspect live best_hours output focusing on real solunar windows."""
import json
import urllib.request

with urllib.request.urlopen(
    "https://kvh-forecast.ru/v1/forecast?species=pike", timeout=15
) as resp:
    r = json.load(resp)

KIND_LABELS = {
    "dawn": "🌅 dawn",
    "dusk": "🌇 dusk",
    "lunar_major": "🌕 major",
    "lunar_minor": "🌗 minor",
}


def fmt_local(iso):
    """Convert UTC ISO to Krasnoyarsk local time (UTC+7)."""
    from datetime import datetime, timezone, timedelta
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    krsk = dt.astimezone(timezone(timedelta(hours=7)))
    return krsk.strftime("%H:%M")


for d in r["days"][:3]:
    print(f"\n=== {d['date']}  moon_phase_label={d.get('moon_phase_label')}  illum={d.get('moon_illumination_pct')}% ===")
    bh = d.get("best_hours", [])
    if not bh:
        print("  (no windows)")
        continue
    for w in bh:
        kind = KIND_LABELS.get(w["kind"], w["kind"])
        print(f"  {kind:<14} {fmt_local(w['start'])}–{fmt_local(w['end'])}  intensity={w['intensity']}  {w['label']}")
