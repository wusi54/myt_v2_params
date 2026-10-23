"""Sensor micro-perturbation to avoid identical sensor fingerprints."""
import random

# 数值字段需要微扰
NUMERIC_FIELDS = ["MaxRange", "Resolution", "Power", "MinDelay", "MaxDelay",
                  "FifoReservedEventCount", "FifoMaxEventCount"]

def perturb_value(val, pct=0.001):
    """Add ±pct random perturbation to a numeric value."""
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        delta = max(1, int(abs(val) * pct))
        return val + random.randint(-delta, delta)
    if isinstance(val, float):
        delta = abs(val) * pct
        return round(val + random.uniform(-delta, delta), 6)
    return val

def perturb_sensors(sensors, pct=0.001):
    """Apply micro-perturbation to sensor numeric fields."""
    if not sensors:
        return sensors
    result = []
    for s in sensors:
        if not isinstance(s, dict):
            result.append(s)
            continue
        new_s = dict(s)
        for field in NUMERIC_FIELDS:
            if field in new_s:
                new_s[field] = perturb_value(new_s[field], pct)
        result.append(new_s)
    return result