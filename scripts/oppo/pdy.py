import json
import random
import os
import sys
import argparse
import re
import hashlib
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.region import (apply_region_to_env, validate_pool_region, build_consistency_report)
from common.debug_props import ensure_debug_props
from common.resolution import apply_resolution
from common.fingerprint_extras import inject_extras, gen_hex64_realistic

def generate_hex(length, uppercase=False):
    chars = "0123456789ABCDEF" if uppercase else "0123456789abcdef"
    return "".join(random.choices(chars, k=length))

def mutate_mac_pair():
    prefix = "60:E3:AC"
    b4 = random.randint(0, 255)
    b5 = random.randint(0, 255)
    b6 = random.randint(0, 254)
    wifi_mac = f"{prefix}:{b4:02X}:{b5:02X}:{b6:02X}".lower()
    bt_mac = f"{prefix}:{b4:02X}:{b5:02X}:{(b6 + 1):02X}".lower()
    return wifi_mac, bt_mac

def generate_mock_cell_info():
    mcc = 460
    mnc = random.choice([0, 1, 2])
    tac = random.randint(10000, 50000)
    ci = random.randint(10000000, 99999999)
    return [{"type": "LTE", "mcc": mcc, "mnc": mnc, "tac": tac, "ci": ci}]

def process_and_validate_oaid(sample_oaid, strict_mode=False):
    clean_sample = str(sample_oaid or "").strip()
    is_all_zero = (set(clean_sample.replace("-", "")) == {'0'}) if clean_sample else True
    if is_all_zero or not clean_sample:
        if "-" in clean_sample or len(clean_sample) == 36:
            def h(n): return "".join(random.choices("0123456789abcdef", k=n))
            return f"{h(8)}-{h(4)}-{h(4)}-{h(4)}-{h(12)}"
        width = len(clean_sample) if len(clean_sample) > 0 else 64
        return "".join(random.choices("0123456789abcdef", k=width))
    if "-" in clean_sample and len(clean_sample) == 36 and re.match(r'^[0-9a-fA-F\-]{36}$', clean_sample):
        def h(n): return "".join(random.choices("0123456789abcdef", k=n))
        new_uuid = f"{h(8)}-{h(4)}-{h(4)}-{h(4)}-{h(12)}"
        if strict_mode and not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', new_uuid):
            raise ValueError("strict OAID validation failed")
        return new_uuid
    if len(clean_sample) == 64 and re.match(r'^[0-9a-fA-F]{64}$', clean_sample):
        return gen_hex64_realistic()
    target_len = len(clean_sample) if len(clean_sample) > 0 else 64
    return "".join(random.choices("0123456789abcdef", k=target_len))

def run_fission(input_file, output_base, copies_count, strict_oaid=False,
                rotate_cell=True, jitter_seconds=3600, seed=None,
                batch_id=None, max_count=5000, ip_region=None, write_manifest=True,
                cell_pool=None, resolution=None):
    if copies_count > max_count:
        print(f"[ERROR] count {copies_count} exceeds max_count {max_count}")
        return
    if not os.path.exists(input_file):
        print(f"[ERROR] Input mother file not found: '{input_file}'")
        return
    if seed is not None:
        random.seed(seed)

    with open(input_file, "r", encoding="utf-8") as f:
        mother = json.load(f)

    cell_pool_data = None
    if cell_pool:
        if os.path.exists(cell_pool):
            if ip_region:
                ok, msg = validate_pool_region(cell_pool, ip_region)
                if not ok:
                    print(f"[ERROR] pool/region mismatch: {msg}")
                    return
                print(f"[OK] pool/region: {msg}")
            try:
                raw = json.load(open(cell_pool, encoding="utf-8"))
                cell_pool_data = [c for c in raw if c.get("tac") is not None and c.get("ci") is not None]
                print(f"[INFO] loaded cell pool: {len(cell_pool_data)} cells")
            except Exception as e:
                print(f"[WARN] cell pool load failed: {e}")
        else:
            print(f"[WARN] cell pool file not found: {cell_pool}")

    output_dir = os.path.dirname(output_base) if os.path.dirname(output_base) else "."
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(output_base).replace(".json", "")
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    sample_oaid = mother.get("telinfo", {}).get("oaid", "")
    print(f"[START] OPPO PDY fission (count: {copies_count}, seed: {seed}, batch: {batch_id})...")

    generated_files = []
    for i in range(1, copies_count + 1):
        child = json.loads(json.dumps(mother))
        child["deviceId"] = generate_hex(64, uppercase=True)

        wifi_mac, bt_mac = mutate_mac_pair()
        new_android_id = generate_hex(16, uppercase=False)
        new_widevine = generate_hex(64, uppercase=False)
        new_serial = "OP" + generate_hex(8, uppercase=True)
        new_oaid = process_and_validate_oaid(sample_oaid, strict_mode=strict_oaid)

        time_offset = random.randint(-jitter_seconds, jitter_seconds)

        for item in child.get("env", []):
            name = str(item.get("name", ""))
            desc_raw = item.get("description", "")
            desc = str(desc_raw).lower()
            target_value = None
            if name == "WIDEVINE" and "id" in desc:
                target_value = new_widevine
            elif "date.utc" in desc or "date_utc" in desc:
                try:
                    target_value = str(int(item.get("value", 0)) + time_offset)
                except (ValueError, TypeError):
                    target_value = str(1786628702 + time_offset)
            if target_value is not None:
                item["value"] = target_value
                if isinstance(desc_raw, str) and desc_raw in item:
                    item[desc_raw] = target_value

        if "telinfo" in child and isinstance(child["telinfo"], dict):
            child["telinfo"]["oaid"] = new_oaid

        extra = []
        alias_map = [
            ("wifi.interface.mac", wifi_mac),
            ("mac", wifi_mac),
            ("bluetooth.interface.mac", bt_mac),
            ("bt_mac", bt_mac),
            ("android_id", new_android_id),
            ("serialno", new_serial),
        ]
        existing = {str(x.get("description", "")).lower() for x in child.get("env", [])}
        for key, val in alias_map:
            if key.lower() not in existing:
                extra.append({"id": 0, "name": "PropRw", "description": key,
                              "value": val, key: val})
        if extra:
            child["env"].extend(extra)

        apply_region_to_env(child["env"], ip_region)
        ensure_debug_props(child["env"])
        if resolution:
            w, h = (int(x) for x in resolution.split("x"))
            apply_resolution(child["env"], w, h)
        inject_extras(child["env"], model_brand="oppo")

        if rotate_cell:
            if cell_pool_data:
                serving = random.choice(cell_pool_data)
                n_nb = min(3, len(cell_pool_data))
                neighbors = random.sample(cell_pool_data, n_nb)
                cells = [serving] + [c for c in neighbors if c is not serving]
                out_cells = []
                for c in cells:
                    out_cells.append({
                        "type": "LTE",
                        "mcc": c.get("mcc", 460),
                        "mnc": c.get("mnc"),
                        "tac": c.get("tac"),
                        "ci": c.get("ci"),
                    })
                seen = set()
                uniq = []
                for c in out_cells:
                    key = (c["mnc"], c["tac"], c["ci"])
                    if key in seen:
                        continue
                    seen.add(key)
                    uniq.append(c)
                child["allcellinfo"] = uniq if uniq else generate_mock_cell_info()
            else:
                child["allcellinfo"] = generate_mock_cell_info()

        fname = f"{base_name}_{batch_ts}_{i:03d}.json"
        if batch_id:
            fname = f"{base_name}_{batch_id}_{batch_ts}_{i:03d}.json"
        file_path = os.path.join(output_dir, fname)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(child, f, indent=4, ensure_ascii=False)
        generated_files.append(fname)

    print(f"[DONE] Generated {copies_count} OPPO PDY child files.")

    if ip_region and cell_pool_data:
        report = build_consistency_report(ip_region, cell_pool_data, ip_region)
        report_path = os.path.join(output_dir, "consistency_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
        print(f"[REPORT] {report_path}")

    if write_manifest:
        manifest = {
            "model": "oppo/PDY",
            "input_file": os.path.basename(input_file),
            "input_sha256": hashlib.sha256(open(input_file, "rb").read()).hexdigest(),
            "count": copies_count,
            "seed": seed,
            "batch_id": batch_id,
            "ip_region": ip_region,
            "strict_oaid": strict_oaid,
            "rotate_cell": rotate_cell,
            "jitter_seconds": jitter_seconds,
            "generated_at": datetime.datetime.now().isoformat(),
            "files": generated_files,
        }
        manifest_path = os.path.join(output_dir, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                old = json.load(open(manifest_path, encoding="utf-8"))
                if isinstance(old, list):
                    old.append(manifest); manifest = old
                elif isinstance(old, dict) and "batches" in old:
                    old["batches"].append(manifest); manifest = old
                else:
                    manifest = {"batches": [old, manifest]}
            except Exception:
                pass
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4, ensure_ascii=False)
        print(f"[MANIFEST] {manifest_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OPPO PDY fission script")
    parser.add_argument("-f", "--file", required=True, help="输入母本 JSON")
    parser.add_argument("-o", "--output", default="output.json", help="输出前缀")
    parser.add_argument("-c", "--count", type=int, default=10, help="生成数量")
    parser.add_argument("-s", "--strict-oaid", action="store_true", help="严格模式")
    parser.add_argument("--no-cell", action="store_true", help="不生成基站")
    parser.add_argument("--jitter", type=int, default=300, help="时钟微扰秒数（默认300）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--batch-id", default=None, help="批次号")
    parser.add_argument("--max-count", type=int, default=5000, help="单次生成上限")
    parser.add_argument("--ip-region", default=None, help="目标地区")
    parser.add_argument("--cell-pool", default=None, help="真实基站池 JSON")
    parser.add_argument("--no-manifest", action="store_true", help="不写 manifest")
    parser.add_argument("--resolution", default=None, help="分辨率，格式 WxH，如 720x1280")
    args = parser.parse_args()
    run_fission(args.file, args.output, args.count,
                strict_oaid=args.strict_oaid,
                rotate_cell=not args.no_cell,
                jitter_seconds=args.jitter,
                seed=args.seed,
                batch_id=args.batch_id,
                max_count=args.max_count,
                ip_region=args.ip_region,
                write_manifest=not args.no_manifest,
                cell_pool=args.cell_pool,
                resolution=args.resolution)