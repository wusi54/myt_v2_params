import json, sys, os, glob

def validate_file(path):
    d = json.load(open(path, encoding='utf-8'))
    if not isinstance(d, dict) or "env" not in d:
        return []  # skip non-device files (manifest, reports, etc.)
    errors = []
    # deviceId
    did = d.get('deviceId', '')
    if not (isinstance(did, str) and len(did) == 64 and all(c in '0123456789ABCDEFabcdef' for c in did)):
        errors.append('deviceId invalid')
    # oaid
    oaid = d.get('telinfo', {}).get('oaid', '')
    if not (isinstance(oaid, str) and len(oaid) > 0 and set(oaid.replace('-', '')) != {'0'}):
        errors.append('oaid all-zero or empty')
    # env prop consistency
    bad = 0
    for it in d.get('env', []):
        desc = it.get('description')
        if isinstance(desc, str) and desc in it:
            if it.get('value') != it.get(desc):
                bad += 1
    if bad:
        errors.append(f'{bad} prop mismatches')
    # baseband consistency
    gsm = [it['value'] for it in d['env'] if it.get('description') == 'gsm.version.baseband']
    if gsm:
        parts = str(gsm[0]).split(',')
        if len(parts) == 2 and parts[0] != parts[1]:
            errors.append('gsm.version.baseband segments differ')
    return errors

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else '.'
    files = []
    if os.path.isfile(target):
        files = [target]
    else:
        files = sorted(glob.glob(os.path.join(target, '**', '*.json'), recursive=True))
    files = [f for f in files if os.path.basename(f) != 'manifest.json']
    total_err = 0
    for f in files:
        errs = validate_file(f)
        if errs:
            total_err += 1
            print(f'[FAIL] {f}: {errs}')
    print(f'Checked {len(files)} files, {total_err} with issues.')

if __name__ == '__main__':
    main()