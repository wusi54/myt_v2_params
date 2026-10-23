"""Cell pool fetching helpers (no CLI)."""
import json, os, time, urllib.request, urllib.error

API = "http://api.cellocation.com:84/recell/"

def fetch_one(lat, lon, n=10, mnc=-1, r=1, timeout=15, retries=3):
    url = f"{API}?lat={lat}&lon={lon}&n={n}&mnc={mnc}&r={r}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data
        except Exception:
            time.sleep(2)
    return None

def normalize(item):
    return {
        "type": "LTE",
        "mcc": 460,
        "mnc": item.get("mnc"),
        "tac": item.get("lac"),
        "ci": item.get("ci"),
        "lat": (item.get("location") or {}).get("lat"),
        "lon": (item.get("location") or {}).get("lon"),
        "acc": item.get("acc"),
    }

def fetch_pool(coords, n=10, mnc=-1, r=1, sleep=1.0):
    pool = []
    seen = set()
    for (lat, lon) in coords:
        data = fetch_one(lat, lon, n=n, mnc=mnc, r=r)
        if not data or (isinstance(data, dict) and "error" in data):
            continue
        items = data if isinstance(data, list) else (data.get("result", []) if isinstance(data, dict) else [])
        for it in items:
            cell = normalize(it)
            key = (cell["mnc"], cell["tac"], cell["ci"])
            if key in seen or cell["tac"] is None or cell["ci"] is None:
                continue
            seen.add(key)
            pool.append(cell)
        time.sleep(sleep)
    return pool

def save_pool(path, cells, append=False):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    existing = []
    if append and os.path.exists(path):
        try:
            existing = json.load(open(path, encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
    # dedupe
    seen = {(c.get("mnc"), c.get("tac"), c.get("ci")) for c in existing}
    merged = list(existing)
    for c in cells:
        key = (c.get("mnc"), c.get("tac"), c.get("ci"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(c)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    return len(merged)