"""Comprehensive diagnostic: what is the live backend actually returning?

Pulls representative responses from kvh-forecast.ru and compares them
to what the deployed frontend expects.
"""
import json
import urllib.request


def get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.load(resp)


print("=" * 60)
print("/v1/forecast?species=pike — TOP LEVEL")
print("=" * 60)
status, r = get("https://kvh-forecast.ru/v1/forecast?species=pike")
print(f"http={status}")
print(f"top-level keys: {sorted(r.keys())}")
print()
print(f"  zone (top): {r.get('zone', '<MISSING>')!r}")
print(f"  zone_label: {r.get('zone_label')!r}")
print(f"  water_level_m: {r.get('water_level_m')}")
print(f"  water_level_source: {r.get('water_level_source')!r}")
print(f"  water_level_is_fresh: {r.get('water_level_is_fresh')}")
print(f"  days count: {len(r.get('days', []))}")

if r.get("days"):
    d = r["days"][0]
    print()
    print("=" * 60)
    print("DAY 0")
    print("=" * 60)
    print(f"day-0 keys: {sorted(d.keys())}")
    print()
    must_have = (
        "date", "species", "score", "confidence",
        "air_temp_c", "water_temp_c", "pressure_hpa", "surface_pressure_hpa",
        "pressure_trend_24h_hpa", "pressure_trend_6h_hpa",
        "wind_speed_m_s", "wind_direction_deg",
        "cloud_cover_pct", "precipitation_mm", "humidity_pct",
        "daylight_hours", "sunrise", "sunset",
        "moon_phase",
        "water_level_m", "water_level_trend_7d_m", "water_level_source",
        "zone", "zone_label", "stale", "factors",
    )
    print("Field-by-field presence (per ForecastDay schema):")
    for f in must_have:
        present = f in d
        val = d.get(f, "<MISSING>")
        if isinstance(val, list) and val:
            val = f"<list len={len(val)}>"
        marker = " " if present else "✗"
        print(f"  [{marker}] {f:<28} {val!r:.50}")
    print()
    print(f"factor count: {len(d.get('factors', []))}")
    print("factor names:")
    for fac in d.get("factors", []):
        c = fac["contribution"]
        sign = "+" if c >= 0 else ""
        print(f"  {sign}{c:.3f}  {fac['name']:<22} {fac.get('detail') or ''}")

print()
print("=" * 60)
print("/v1/forecast?species=bream&zone=syda — zone routing")
print("=" * 60)
status, r = get("https://kvh-forecast.ru/v1/forecast?species=bream&zone=syda")
print(f"http={status}")
print(f"  zone (top): {r.get('zone')!r}")
print(f"  zone_label: {r.get('zone_label')!r}")
print(f"  day-0 score: {r.get('days', [{}])[0].get('score')}")

print()
print("=" * 60)
print("Other endpoints")
print("=" * 60)
for path in (
    "/v1/water-level/history?days=7",
    "/v1/weather/history?days=7",
    "/v1/push/vapid-public-key",
    "/v1/push/condition-types",
):
    try:
        status, r = get(f"https://kvh-forecast.ru{path}")
        if isinstance(r, dict):
            keys = sorted(r.keys())
            count_field = next(
                (k for k in keys if k in ("days_requested", "types", "points")), None
            )
            extra = ""
            if count_field:
                v = r[count_field]
                extra = f" {count_field}={len(v) if isinstance(v, list) else v}"
            print(f"  {path:<50}  http={status} keys={keys}{extra}")
        else:
            print(f"  {path:<50}  http={status} (non-dict)")
    except Exception as e:
        print(f"  {path:<50}  FAIL: {e}")
