"""Ensure debug/secure properties are set to safe values for risk control."""

DEBUG_PROPS = {
    "ro.debuggable": "0",
    "ro.secure": "1",
    "ro.adb.secure": "1",
    "ro.build.type": "user",
    "ro.build.tags": "release-keys",
    "persist.sys.timezone": "Asia/Shanghai",
    "ro.product.locale": "zh-CN",
}

# 模拟器/调试特征属性（如果存在则移除或设为安全值）
SUSPICIOUS_PROPS = {
    "ro.kernel.qemu": "0",
    "ro.boot.qemu": "0",
    "ro.qemu.hw.mainkeys": "0",
    "qemu.hw.mainkeys": "0",
}

def ensure_debug_props(env):
    """Ensure debug/secure props are set; remove suspicious emulator props."""
    existing = {str(it.get("description", "")).lower(): it for it in env}
    for key, val in DEBUG_PROPS.items():
        if key.lower() not in existing:
            env.append({
                "id": 0, "name": "PropRw", "description": key,
                "value": val, key: val,
            })
        else:
            item = existing[key.lower()]
            item["value"] = val
            if key in item:
                item[key] = val
    for key, val in SUSPICIOUS_PROPS.items():
        if key.lower() in existing:
            item = existing[key.lower()]
            item["value"] = val
            if key in item:
                item[key] = val
    return env