"""End-to-end smoke test for the push-notification constructor.


Steps:
 1. Login → bearer token.
 2. Fetch /v1/push/condition-types — verify catalog loads.
 3. Subscribe with a multi-condition recipe (zone + species + 3 conditions).
 4. List subscriptions and verify the conditions round-trip cleanly.
 5. Trigger /v1/admin/ingest/weather and inspect push dispatch outcome.
 6. Clean up the test subscription.
"""
import json
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
USER = "demo"
PASS = "demo123"
FAKE_ENDPOINT = "https://fcm.googleapis.com/fcm/send/SMOKETEST" + "x" * 50


def call(method, path, body=None, token=None):
    req = urllib.request.Request(
        f"{BASE}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        return resp.status, json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, {"raw": text}


# 1. Login
status, login = call("POST", "/v1/auth/login", {"username": USER, "password": PASS})
token = login["access_token"]
print(f"login: {status} (token len={len(token)})")

# 2. Catalog
status, catalog = call("GET", "/v1/push/condition-types")
print(f"catalog: {status} ({len(catalog['types'])} condition types)")
print(f"  first 5 types: {[t['type'] for t in catalog['types'][:5]]}")

# 3. Subscribe (constructor: name + scope + 3 conditions)
sub_body = {
    "endpoint": FAKE_ENDPOINT,
    "keys": {
        "p256dh": "BO" + "x" * 85,
        "auth": "y" * 22,
    },
    "name": "smoke: лещ на Сыде в выходные",
    "scope_zone": "syda",
    "scope_species": "bream",
    "conditions": [
        {"type": "score_min", "params": {"min": 3.0}},
        {"type": "no_pressure_shock", "params": {}},
        {"type": "weekend_only", "params": {}},
    ],
}
status, sub = call("POST", "/v1/push/subscriptions", sub_body, token=token)
print(f"subscribe: {status}, sub_id={sub.get('id') if isinstance(sub, dict) else sub}")

# 4. Round-trip via list
status, my_subs = call("GET", "/v1/push/subscriptions/me", token=token)
target = next((s for s in my_subs if s["id"] == sub["id"]), None)
print(f"list: {status} ({len(my_subs)} subs)")
print(f"  target.scope_zone={target['scope_zone']}, scope_species={target['scope_species']}")
print(f"  target.conditions={target['conditions']}")

# 5. Trigger ingest (push dispatch happens internally). The fake endpoint
# will fail to deliver but the dispatcher should evaluate conditions and
# report sent/skipped counts.
status, ingest = call("POST", "/v1/admin/ingest/weather", token=token)
print(f"ingest: {status}, push outcome = {ingest.get('push')}")

# 6. Cleanup
status, _ = call("DELETE", f"/v1/push/subscriptions/{sub['id']}", token=token)
print(f"cleanup: {status}")
