import argparse, os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from common.cell_fetch import fetch_pool, save_pool

def parse_coords(args):
    coords = []
    if args.coords_file:
        with open(args.coords_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [x.strip() for x in line.replace(";", ",").split(",")]
                if len(parts) >= 2:
                    coords.append((float(parts[0]), float(parts[1])))
    elif args.lat is not None and args.lon is not None:
        coords.append((args.lat, args.lon))
    return coords

def main():
    parser = argparse.ArgumentParser(description="Fetch real cell pool from cellocation recell API")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--coords-file")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--mnc", type=int, default=-1)
    parser.add_argument("--r", type=int, default=1)
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()

    coords = parse_coords(args)
    if not coords:
        print("[ERROR] provide --lat/--lon or --coords-file")
        return
    cells = fetch_pool(coords, n=args.n, mnc=args.mnc, r=args.r, sleep=args.sleep)
    total = save_pool(args.output, cells, append=args.append)
    print(f"[DONE] fetched {len(cells)} new, total {total} -> {args.output}")

if __name__ == "__main__":
    main()