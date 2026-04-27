"""Compare per-zone bream forecasts across all 13 bays."""
import json
import urllib.request

ZONES = (
    "tubinsky", "karasug", "ubey", "yezagash", "syda", "koma",
    "izhul", "ogur", "anash", "derbino", "sisim", "biryusa", "main_channel",
)

results = []
for z in ZONES:
    url = f"http://localhost:8000/v1/forecast?species=bream&zone={z}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        r = json.load(resp)
    d = r["days"][0]
    results.append({
        "code": z,
        "label": r["zone_label"],
        "score": d["score"],
        "air": d["air_temp_c"],
        "wind": d["wind_speed_m_s"],
        "clouds": d["cloud_cover_pct"],
        "dp24": d["pressure_trend_24h_hpa"],
    })

# Sort best → worst.
results.sort(key=lambda x: -x["score"])

print(f"\nBream forecast (day 0) ranked by score across all 13 bays:\n")
print(f"  {'rank':>2}  {'score':>5}  {'air':>4}  {'wind':>5}  {'clds':>4}  {'ΔP24':>5}  bay")
print(f"  {'-'*2}  {'-'*5}  {'-'*4}  {'-'*5}  {'-'*4}  {'-'*5}  {'-'*40}")
for i, r in enumerate(results, 1):
    print(
        f"  {i:>2}  {r['score']:>5.2f}  {r['air']:>+4.1f}  {r['wind']:>4.1f}  "
        f"{r['clouds']:>3.0f}%  {r['dp24']:>+4.1f}  {r['label']}"
    )
