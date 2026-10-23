"""Inject additional fingerprint fields not present in mother templates."""
import random

WIFI_SSIDS = ["ChinaNet-5G", "CMCC-5G", "CU-5G", "TP-LINK_5G", "FAST_5G", "HUAWEI-5G", "Xiaomi_5G", "OPPO-5G"]
NETWORK_TYPES = ["WIFI", "4G", "5G"]
BATTERY_LEVELS = [str(random.randint(20, 100)) for _ in range(5)]

def gen_uuid4():
    """Generate a UUID v4 compliant string (matches real OAID distribution)."""
    def h(n): return "".join(random.choices("0123456789abcdef", k=n))
    # version 4: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx where y in {8,9,a,b}
    return f"{h(8)}-{h(4)}-4{h(3)}-{random.choice('89ab')}{h(3)}-{h(12)}"

def gen_hex64_realistic():
    """Generate a 64-hex string with plausible byte distribution (non-zero leading)."""
    first = random.choice("123456789abcdef")
    rest = "".join(random.choices("0123456789abcdef", k=63))
    return first + rest

def inject_extras(env, model_brand=""):
    """Inject missing fingerprint fields into env list."""
    existing = {str(it.get("description", "")).lower() for it in env}

    def add(key, val):
        if key.lower() not in existing:
            env.append({"id": 0, "name": "PropRw", "description": key,
                        "value": val, key: val})
            existing.add(key.lower())

    # Build.SERIAL (ro.serialno) - may already exist
    add("ro.serialno", "unknown")

    # WiFi SSID / BSSID
    add("wifi.ssid", random.choice(WIFI_SSIDS))
    add("wifi.bssid", "00:00:00:00:00:00")

    # Network type
    add("network.type", random.choice(NETWORK_TYPES))

    # Battery
    add("battery.level", random.choice(BATTERY_LEVELS))
    add("battery.status", random.choice(["charging", "discharging", "full"]))

    # Huawei VAID/AAID
    if model_brand.lower() == "huawei":
        add("vaid", gen_uuid4())
        add("aaid", gen_uuid4())

    # VAID for all (some SDKs check)
    add("vaid", gen_uuid4())

    return env