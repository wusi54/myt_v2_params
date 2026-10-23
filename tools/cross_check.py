import json, sys, os, glob

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else '.'
    files = sorted(glob.glob(os.path.join(target, '**', '*.json'), recursive=True))
    files = [f for f in files if os.path.basename(f) != 'manifest.json']
    if not files:
        print('No json files found'); return
    devs, oids, wvs = set(), set(), set()
    static_keys = ['serviceList', 'featuresex', 'librarys', 'cpuinfo']
    static_vals = {k: set() for k in static_keys}
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        if not isinstance(d, dict) or "env" not in d:
            continue
        devs.add(d.get('deviceId'))
        oids.add(d.get('telinfo', {}).get('oaid'))
        wv = [it['value'] for it in d.get('env', []) if it.get('name') == 'WIDEVINE']
        if wv: wvs.add(wv[0])
        for k in static_keys:
            static_vals[k].add(d.get(k))
    print(f'Files: {len(files)}')
    print(f'Unique deviceId: {len(devs)}')
    print(f'Unique oaid: {len(oids)}')
    print(f'Unique widevine: {len(wvs)}')
    for k in static_keys:
        print(f'Unique {k}: {len(static_vals[k])}')

if __name__ == '__main__':
    main()