"""Region consistency helpers for device fission."""
import os
import json

REGION_CONFIG = {
    "beijing": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                "lat_range": (39.4, 41.1), "lon_range": (115.4, 117.6)},
    "shanghai": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                 "lat_range": (30.7, 31.9), "lon_range": (120.9, 122.0)},
    "guangzhou": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                  "lat_range": (22.5, 23.9), "lon_range": (112.9, 114.1)},
    "shenzhen": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                 "lat_range": (22.4, 22.9), "lon_range": (113.7, 114.6)},
    "hangzhou": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                 "lat_range": (29.8, 30.6), "lon_range": (119.5, 120.8)},
    "chengdu": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                "lat_range": (30.0, 31.5), "lon_range": (103.5, 104.9)},
    "wuhan": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
              "lat_range": (29.9, 31.4), "lon_range": (113.7, 115.1)},
    "nanjing": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
                "lat_range": (31.2, 32.6), "lon_range": (118.4, 119.3)},
    "cn": {"locale": "zh-CN", "timezone": "Asia/Shanghai", "mnc": [0, 1, 2],
           "lat_range": (18.0, 54.0), "lon_range": (73.0, 135.0)},
}

def get_region_config(region):
    if region is None:
        return None
    return REGION_CONFIG.get(str(region).lower())

def apply_region_to_env(env, region):
    cfg = get_region_config(region)
    if not cfg:
        return
    for item in env:
        desc = str(item.get("description", "")).lower()
        if desc == "ro.product.locale":
            item["value"] = cfg["locale"]
            if "ro.product.locale" in item:
                item["ro.product.locale"] = cfg["locale"]

def validate_pool_region(pool_path, region):
    cfg = get_region_config(region)
    if cfg is None:
        return True, "no region config"
    base = os.path.basename(pool_path).lower()
    if region and str(region).lower() not in base and str(region).lower() != "cn":
        return False, f"pool filename '{base}' does not contain region '{region}'"
    try:
        pool = json.load(open(pool_path, encoding="utf-8"))
    except Exception as e:
        return False, f"cannot read pool: {e}"
    if not pool:
        return False, "empty pool"
    lats = [c.get("lat") for c in pool if c.get("lat") is not None]
    lons = [c.get("lon") for c in pool if c.get("lon") is not None]
    if lats and lons:
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        r_lat = cfg["lat_range"]
        r_lon = cfg["lon_range"]
        if lat_max < r_lat[0] or lat_min > r_lat[1] or lon_max < r_lon[0] or lon_min > r_lon[1]:
            return False, (f"pool coords [{lat_min:.2f},{lat_max:.2f}]x[{lon_min:.2f},{lon_max:.2f}] "
                           f"outside region '{region}' range")
    # mnc check
    mncs = {c.get("mnc") for c in pool if c.get("mnc") is not None}
    if mncs and cfg.get("mnc"):
        bad = [m for m in mncs if m not in cfg["mnc"]]
        if bad:
            return False, f"pool mnc {bad} not allowed for region '{region}'"
    return True, "ok"

def build_consistency_report(region, pool, ip_region):
    cfg = get_region_config(region)
    lats = [c.get("lat") for c in pool if c.get("lat") is not None]
    lons = [c.get("lon") for c in pool if c.get("lon") is not None]
    mnc_counts = {}
    for c in pool:
        m = c.get("mnc")
        mnc_counts[m] = mnc_counts.get(m, 0) + 1
    return {
        "ip_region": ip_region,
        "region_config": cfg,
        "pool_size": len(pool),
        "pool_lat_range": [min(lats), max(lats)] if lats else None,
        "pool_lon_range": [min(lons), max(lons)] if lons else None,
        "pool_mnc_distribution": mnc_counts,
        "allowed_mnc": cfg["mnc"] if cfg else None,
        "mnc_in_allowed": all(m in (cfg["mnc"] if cfg else []) for m in mnc_counts) if cfg else None,
        "timezone": cfg["timezone"] if cfg else None,
        "locale": cfg["locale"] if cfg else None,
        "note": "Ensure proxy IP exit city matches ip_region and pool coordinate range.",
    }