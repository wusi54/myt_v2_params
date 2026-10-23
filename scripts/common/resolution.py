"""Apply a unified screen resolution to env list."""

def apply_resolution(env, width=720, height=1280):
    """Override LCDX/LCDY and related dpi fields."""
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
    return env