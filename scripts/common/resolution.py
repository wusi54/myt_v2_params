"""Apply a unified screen resolution to env list."""

import re

def apply_resolution(env, width=720, height=1280):
    """Override LCDX/LCDY and related resolution strings."""
    res_str = f"{width}*{height}"
    old_res_pattern = re.compile(r"\d+\*\d+")
    for item in env:
        desc = str(item.get("description", "")).lower()
        name = str(item.get("name", "")).lower()
        if desc == "lcdx" or name == "lcdx":
            item["value"] = str(width)
            if "LCDX" in item:
                item["LCDX"] = str(width)
        elif desc == "lcdy" or name == "lcdy":
            item["value"] = str(height)
            if "LCDY" in item:
                item["LCDY"] = str(height)
        else:
            # Update resolution-like strings in values (e.g., "720*1612_320dpi")
            val = item.get("value")
            if isinstance(val, str) and "*" in val and "dpi" in val.lower():
                item["value"] = old_res_pattern.sub(f"{width}*{height}", val, count=1)
                # also update the prop key if present
                for k in list(item.keys()):
                    if k.startswith("ro.") and isinstance(item[k], str) and "*" in item[k] and "dpi" in item[k].lower():
                        item[k] = old_res_pattern.sub(f"{width}*{height}", item[k], count=1)
            # Update build description/flavor resolution hints (e.g., HD1600 -> HD1280)
            if isinstance(val, str) and "HD" in val and any(ch.isdigit() for ch in val):
                item["value"] = re.sub(r"HD\d+", f"HD{height}", val)
                for k in list(item.keys()):
                    if k.startswith("ro.") and isinstance(item[k], str) and "HD" in item[k]:
                        item[k] = re.sub(r"HD\d+", f"HD{height}", item[k])
    return env