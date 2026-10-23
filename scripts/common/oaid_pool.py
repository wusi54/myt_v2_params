"""OAID pool loading and assignment helpers."""
import json, os, random

def load_oaid_pool(path):
    """Load OAID pool from JSON file. Supports list of strings or list of objects with 'oaid' key."""
    if not path or not os.path.exists(path):
        return []
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception:
        return []
    if isinstance(data, list):
        out = []
        for item in data:
            if isinstance(item, str):
                out.append(item.strip().lower())
            elif isinstance(item, dict) and 'oaid' in item:
                out.append(str(item['oaid']).strip().lower())
        return out
    return []

def pick_oaid(pool, used_set):
    """Pick an unused OAID from pool. Returns (oaid, remaining_pool)."""
    if not pool:
        return None, pool
    # find unused
    candidates = [o for o in pool if o not in used_set]
    if not candidates:
        return None, pool
    chosen = random.choice(candidates)
    used_set.add(chosen)
    new_pool = [o for o in pool if o != chosen]
    return chosen, new_pool