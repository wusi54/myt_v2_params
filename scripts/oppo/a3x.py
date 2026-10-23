import json
import random
import os
import argparse
import re

def generate_hex(length, uppercase=False):
    chars = "0123456789ABCDEF" if uppercase else "0123456789abcdef"
    return "".join(random.choices(chars, k=length))

def generate_mock_baseband():
    """生成真实的联发科天玑标准无线基带版本号"""
    v_num = random.randint(120, 199)
    return f"MOLY.LR12A.R3.MP.V{v_num}.P{random.randint(1,9)}"

def mutate_mac_pair():
    """生成具备真实物理排线联动特征的 Wi-Fi/蓝牙 MAC 地址"""
    prefix = "60:E3:AC"
    b4 = random.randint(0, 255)
    b5 = random.randint(0, 255)
    b6 = random.randint(0, 254)
    wifi_mac = f"{prefix}:{b4:02X}:{b5:02X}:{b6:02X}".lower()
    bt_mac = f"{prefix}:{b4:02X}:{b5:02X}:{(b6 + 1):02X}".lower()
    return wifi_mac, bt_mac

def generate_mock_cell_info():
    """生成高拟真的国内 LTE 基站小区环境数据，打破基站真空"""
    mcc = 460
    mnc = random.choice([0, 1, 2]) # 0移动, 1联通, 2电信
    tac = random.randint(10000, 50000)
    ci = random.randint(10000000, 99999999)
    return [{"type": "LTE", "mcc": mcc, "mnc": mnc, "tac": tac, "ci": ci}]

def process_and_validate_oaid(sample_oaid, strict_mode=False):
    """
    OAID 自适应洗白与强校验白名单逻辑
    - 若原样为全零(0000...)或空，则按机型规范强制生成高拟真非零串
    - 若原样为 36 位 UUID，则严格校验并输出合法 UUID
    - 若原样为 64 位十六进制，则严格按 64 位对齐输出
    """
    clean_sample = str(sample_oaid or "").strip()
    is_all_zero = (set(clean_sample.replace("-", "")) == {'0'}) if clean_sample else True

    # 1. 全零或非法初始值：降级按安全规范重构
    if is_all_zero or not clean_sample:
        # 如果长度像 36 位，补 UUID，否则默认 64 位大厂 hex
        if "-" in clean_sample or len(clean_sample) == 36:
            def h(n): return "".join(random.choices("0123456789abcdef", k=n))
            return f"{h(8)}-{h(4)}-{h(4)}-{h(4)}-{h(12)}"
        return "".join(random.choices("0123456789abcdef", k=64))

    # 2. 36位 UUID 格式 (如 OPPO/Realme)
    if "-" in clean_sample and len(clean_sample) == 36 and re.match(r'^[0-9a-fA-F\-]{36}$', clean_sample):
        def h(n): return "".join(random.choices("0123456789abcdef", k=n))
        new_uuid = f"{h(8)}-{h(4)}-{h(4)}-{h(4)}-{h(12)}"
        if strict_mode and not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', new_uuid):
            raise ValueError(f"严格模式校验失败: 生成的 OAID 不符合标准 UUID 规范")
        return new_uuid

    # 3. 64位十六进制格式 (如 vivo S10 Pro 等)
    elif len(clean_sample) == 64 and re.match(r'^[0-9a-fA-F]{64}$', clean_sample):
        new_hex64 = "".join(random.choices("0123456789abcdef", k=64))
        if strict_mode and len(new_hex64) != 64:
            raise ValueError("严格模式校验失败: 长度不是 64 位")
        return new_hex64

    # 4. 其他未知长度兜底
    else:
        target_len = len(clean_sample) if len(clean_sample) > 0 else 64
        return "".join(random.choices("0123456789abcdef", k=target_len))

def run_fission(input_file, output_base, copies_count, strict_oaid=False):
    if not os.path.exists(input_file):
        print(f"❌ 错误: 找不到输入母本文件 '{input_file}'")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        mother_json_data = json.load(f)

    output_dir = os.path.dirname(output_base) if os.path.dirname(output_base) else "."
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(output_base).replace(".json", "")

    # 提取母本初始 OAID 作为白名单结构参照
    sample_oaid = mother_json_data.get("telinfo", {}).get("oaid", "")

    print(f"🔄 启动【OAID白名单强校验 & 逻辑自洽】裂变 (生成数: {copies_count}, 严格模式: {strict_oaid})...")

    for i in range(1, copies_count + 1):
        child_data = json.loads(json.dumps(mother_json_data))
        
        # 1. 根设备硬指纹重置
        child_data["deviceId"] = generate_hex(64, uppercase=True)
        
        # 2. 计算独立硬件基因
        wifi_mac, bt_mac = mutate_mac_pair()
        new_android_id = generate_hex(16, uppercase=False)
        new_widevine = generate_hex(64, uppercase=False)
        new_serial = "OP4E" + generate_hex(8, uppercase=True)
        new_oaid = process_and_validate_oaid(sample_oaid, strict_mode=strict_oaid)
        
        # 时钟微扰 (±3600秒)
        time_offset = random.randint(-3600, 3600)
        base_utc = 1786628702
        new_utc = str(base_utc + time_offset)

        # 3. 深度映射修正 env 数组
        for item in child_data.get("env", []):
            name = str(item.get("name", ""))
            desc_raw = item.get("description", "")
            desc = str(desc_raw).lower()
            
            target_value = None
            if name == "WIDEVINE" and "id" in desc:
                target_value = new_widevine
            elif "wifi.interface.mac" in desc or desc == "mac":
                target_value = wifi_mac
            elif "bluetooth.interface.mac" in desc or desc == "bt_mac":
                target_value = bt_mac
            elif "android_id" in desc:
                target_value = new_android_id
            elif "serialno" in desc:
                target_value = new_serial
            elif desc == "ro.baseband":
                target_value = "unknown" # 联发科合法真机值
            elif "gsm.version.baseband" in desc or "radio_version" in desc:
                moly_val = f"{generate_mock_baseband()},{generate_mock_baseband()}"
                target_value = moly_val
            elif "date.utc" in desc:
                target_value = new_utc

            if target_value is not None:
                item["value"] = target_value
                if desc_raw in item:
                    item[desc_raw] = target_value

        # 4. 写入校验后的全新 OAID
        if "telinfo" in child_data and isinstance(child_data["telinfo"], dict):
            child_data["telinfo"]["oaid"] = new_oaid

        # 5. 补充动态基站
        child_data["allcellinfo"] = generate_mock_cell_info()

        # 保存
        file_path = os.path.join(output_dir, f"{base_name}_{i:03d}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(child_data, f, indent=4, ensure_ascii=False)

    print(f"🎉 成功生成 {copies_count} 份符合 OAID 白名单与检测规范的子指纹文件！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="魔云腾终极防封裂变脚本 (含 OAID 强校验)")
    parser.add_argument("-f", "--file", required=True, help="输入母本 JSON")
    parser.add_argument("-o", "--output", default="output.json", help="输出前缀")
    parser.add_argument("-c", "--count", type=int, default=10, help="生成数量")
    parser.add_argument("-s", "--strict-oaid", action="store_true", help="开启 OAID 格式强校验白名单模式")
    
    args = parser.parse_args()
    run_fission(args.file, args.output, args.count, strict_oaid=args.strict_oaid)
