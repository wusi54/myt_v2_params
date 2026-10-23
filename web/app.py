import os, sys, json, subprocess, threading, uuid, time, datetime, sqlite3, shutil
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON = sys.executable
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common.cell_fetch import fetch_pool, save_pool
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "app.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
scheduler = BackgroundScheduler(daemon=True)

# ---------- DB ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, model TEXT, status TEXT, params TEXT, log TEXT,
        created_at TEXT, finished_at TEXT, returncode INTEGER, output_path TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY, name TEXT, model TEXT, trigger_type TEXT, trigger_expr TEXT,
        params TEXT, enabled INTEGER, last_run TEXT, next_run TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS pools (
        id TEXT PRIMARY KEY, name TEXT, filename TEXT, path TEXT, region TEXT,
        count INTEGER, created_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

# ---------- helpers ----------
def load_models():
    p = os.path.join(ROOT, "config", "models.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")).get("models", [])
    return []

def model_by_name(name):
    for m in load_models():
        if m["model"] == name:
            return m
    return None

def scan_pools_to_db():
    conn = get_conn()
    base = os.path.join(ROOT, "templates", "cell_pools")
    os.makedirs(base, exist_ok=True)
    for root_, _, files in os.walk(os.path.join(ROOT, "templates")):
        for f in files:
            if not f.endswith(".json") or "pool" not in f.lower():
                continue
            full = os.path.join(root_, f)
            rel = os.path.relpath(full, ROOT)
            row = conn.execute("SELECT id FROM pools WHERE path=?", (rel,)).fetchone()
            if row:
                continue
            try:
                data = json.load(open(full, encoding="utf-8"))
                count = len(data) if isinstance(data, list) else 0
            except Exception:
                count = 0
            region = None
            low = f.lower()
            for r in ["beijing","shanghai","guangzhou","shenzhen","hangzhou","chengdu","wuhan","nanjing"]:
                if r in low:
                    region = r; break
            conn.execute("INSERT INTO pools (id,name,filename,path,region,count,created_at) VALUES (?,?,?,?,?,?,?)",
                         (uuid.uuid4().hex[:8], f, f, rel, region, count, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

scan_pools_to_db()

# ---------- generation worker ----------
def run_generation(task_id, model, params):
    conn = get_conn()
    mcfg = model_by_name(model)
    if not mcfg or not mcfg.get("script"):
        conn.execute("UPDATE tasks SET status=?, finished_at=?, log=? WHERE id=?",
                     ("error", datetime.datetime.now().isoformat(), "no script", task_id))
        conn.commit(); conn.close(); return
    script = os.path.join(ROOT, mcfg["script"])
    template = os.path.join(ROOT, mcfg["template_path"])
    out_dir = os.path.join(ROOT, mcfg["output_dir"], "web_batch")
    os.makedirs(out_dir, exist_ok=True)
    out_prefix = os.path.join(out_dir, "out")

    cmd = [PYTHON, script, "-f", template, "-o", out_prefix, "-c", str(params.get("count", 10))]
    if params.get("strict_oaid"):
        cmd.append("-s")
    if params.get("gen_cell"):
        cmd.append("--gen-cell")
    cmd += ["--jitter", str(params.get("jitter", 3600))]
    if params.get("seed") not in (None, ""):
        cmd += ["--seed", str(params["seed"])]
    if params.get("batch_id"):
        cmd += ["--batch-id", str(params["batch_id"])]
    cmd += ["--max-count", str(params.get("max_count", 5000))]
    if params.get("ip_region"):
        cmd += ["--ip-region", str(params["ip_region"])]
    if params.get("cell_pool"):
        cmd += ["--cell-pool", str(params["cell_pool"])]

    conn.execute("UPDATE tasks SET status=? WHERE id=?", ("running", task_id))
    conn.commit()
    conn.close()

    log = ""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
        for line in proc.stdout:
            log += line
            c = get_conn()
            c.execute("UPDATE tasks SET log=? WHERE id=?", (log, task_id))
            c.commit(); c.close()
        proc.wait()
        status = "done" if proc.returncode == 0 else "error"
    except Exception as e:
        status = "error"; log += str(e); proc = None; rc = -1
        rc = proc.returncode if proc else -1
    else:
        rc = proc.returncode

    conn = get_conn()
    conn.execute("UPDATE tasks SET status=?, finished_at=?, returncode=?, log=?, output_path=? WHERE id=?",
                 (status, datetime.datetime.now().isoformat(), rc, log, out_dir, task_id))
    conn.commit(); conn.close()

# ---------- scheduler ----------
def execute_schedule(sched_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM schedules WHERE id=? AND enabled=1", (sched_id,)).fetchone()
    if not row:
        conn.close(); return
    params = json.loads(row["params"])
    task_id = uuid.uuid4().hex[:8]
    conn.execute("INSERT INTO tasks (id,model,status,params,log,created_at,output_path) VALUES (?,?,?,?,?,?,?)",
                 (task_id, row["model"], "queued", json.dumps(params), "", datetime.datetime.now().isoformat(), ""))
    conn.commit()
    if row["model"] == "__pool_fetch__":
        threading.Thread(target=run_pool_fetch, args=(task_id, params), daemon=True).start()
    else:
        threading.Thread(target=run_generation, args=(task_id, row["model"], params), daemon=True).start()
    # update schedule
    job = scheduler.get_job(sched_id)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    conn.execute("UPDATE schedules SET last_run=?, next_run=? WHERE id=?",
                 (datetime.datetime.now().isoformat(), next_run, sched_id))
    conn.commit(); conn.close()

def load_schedules():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM schedules WHERE enabled=1").fetchall()
    conn.close()
    for row in rows:
        try:
            if row["trigger_type"] == "cron":
                trigger = CronTrigger.from_crontab(row["trigger_expr"])
            else:
                mins = int(row["trigger_expr"])
                trigger = IntervalTrigger(minutes=mins)
            scheduler.add_job(execute_schedule, trigger, args=[row["id"]], id=row["id"], replace_existing=True)
        except Exception as e:
            print(f"[SCHED] failed to load {row['id']}: {e}")

def run_pool_fetch(task_id, params):
    conn = get_conn()
    conn.execute("UPDATE tasks SET status=? WHERE id=?", ("running", task_id))
    conn.commit(); conn.close()
    log = ""
    try:
        coords = params.get("coords", [])
        if isinstance(coords, str):
            coords = [ [float(x) for x in c.split(",")] for c in coords.split(";") if c.strip() ]
        coords = [(float(c[0]), float(c[1])) for c in coords]
        cells = fetch_pool(coords, n=params.get("n", 10), mnc=params.get("mnc", -1),
                           r=params.get("r", 1), sleep=params.get("sleep", 1.0))
        if not cells:
            log = ("[ERROR] No cells fetched. cellocation API may be unreachable from this host "
                   "(requires fixed public IP / port 84). Please pre-fetch on a public server and "
                   "copy the pool JSON into templates/cell_pools/.\n")
            status = "error"; rc = 1
            conn = get_conn()
            conn.execute("UPDATE tasks SET status=?, finished_at=?, returncode=?, log=? WHERE id=?",
                         (status, datetime.datetime.now().isoformat(), rc, log, task_id))
            conn.commit(); conn.close()
            return
        out_path = params.get("output", "templates/cell_pools/pool_cn.json")
        if not os.path.isabs(out_path):
            out_path = os.path.join(ROOT, out_path)
        total = save_pool(out_path, cells, append=params.get("append", True))
        log = f"Fetched {len(cells)} new cells, total {total} -> {out_path}\n"
        status = "done"; rc = 0
        # register pool in DB
        try:
            region = params.get("region")
            conn2 = get_conn()
            conn2.execute("INSERT INTO pools (id,name,filename,path,region,count,created_at) VALUES (?,?,?,?,?,?,?)",
                          (uuid.uuid4().hex[:8], os.path.basename(out_path), os.path.basename(out_path),
                           os.path.relpath(out_path, ROOT), region, total, datetime.datetime.now().isoformat()))
            conn2.commit(); conn2.close()
        except Exception:
            pass
    except Exception as e:
        status = "error"; rc = -1; log += str(e)
    conn = get_conn()
    conn.execute("UPDATE tasks SET status=?, finished_at=?, returncode=?, log=?, output_path=? WHERE id=?",
                 (status, datetime.datetime.now().isoformat(), rc, log, out_path if 'out_path' in locals() else "", task_id))
    conn.commit(); conn.close()

# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/models")
def api_models():
    return jsonify(load_models())

@app.route("/api/regions")
def api_regions():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from common.region import REGION_CONFIG
    return jsonify(list(REGION_CONFIG.keys()))

@app.route("/api/pools")
def api_pools():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM pools ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/pools/upload", methods=["POST"])
def api_pool_upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".json"):
        return jsonify({"error": "json only"}), 400
    region = request.form.get("region") or None
    dest_dir = os.path.join(ROOT, "templates", "cell_pools")
    os.makedirs(dest_dir, exist_ok=True)
    safe_name = f.filename
    dest = os.path.join(dest_dir, safe_name)
    f.save(dest)
    try:
        data = json.load(open(dest, encoding="utf-8"))
        count = len(data) if isinstance(data, list) else 0
    except Exception:
        count = 0
    conn = get_conn()
    pid = uuid.uuid4().hex[:8]
    rel_dest = os.path.relpath(dest, ROOT)
    conn.execute("INSERT INTO pools (id,name,filename,path,region,count,created_at) VALUES (?,?,?,?,?,?,?)",
                 (pid, safe_name, safe_name, rel_dest, region, count, datetime.datetime.now().isoformat()))
    conn.commit(); conn.close()
    return jsonify({"id": pid, "name": safe_name, "count": count, "region": region})

@app.route("/api/pools/<pid>", methods=["DELETE"])
def api_pool_delete(pid):
    conn = get_conn()
    row = conn.execute("SELECT path FROM pools WHERE id=?", (pid,)).fetchone()
    if row:
        full = row["path"]
        if not os.path.isabs(full):
            full = os.path.join(ROOT, full)
        try:
            if os.path.exists(full):
                os.remove(full)
        except Exception:
            pass
        conn.execute("DELETE FROM pools WHERE id=?", (pid,))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/pools/<pid>/preview")
def api_pool_preview(pid):
    conn = get_conn()
    row = conn.execute("SELECT path FROM pools WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    full = row["path"]
    if not os.path.isabs(full):
        full = os.path.join(ROOT, full)
    if not os.path.exists(full):
        return jsonify({"error": "not found"}), 404
    data = json.load(open(full, encoding="utf-8"))
    return jsonify({"count": len(data) if isinstance(data, list) else 0,
                    "sample": (data[:5] if isinstance(data, list) else data)})

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(force=True)
    model = data.get("model")
    mcfg = model_by_name(model)
    if not mcfg or not mcfg.get("script"):
        return jsonify({"error": "no script for model"}), 400
    template = os.path.join(ROOT, mcfg["template_path"])
    if not os.path.exists(template):
        return jsonify({"error": "template not found"}), 400

    params = {
        "count": int(data.get("count", 10)),
        "seed": data.get("seed"),
        "batch_id": data.get("batch_id"),
        "strict_oaid": bool(data.get("strict_oaid", False)),
        "gen_cell": bool(data.get("gen_cell", False)),
        "jitter": int(data.get("jitter", 3600)),
        "max_count": int(data.get("max_count", 5000)),
        "ip_region": data.get("ip_region"),
        "cell_pool": data.get("cell_pool"),
    }

    task_id = uuid.uuid4().hex[:8]
    conn = get_conn()
    conn.execute("INSERT INTO tasks (id,model,status,params,log,created_at,output_path) VALUES (?,?,?,?,?,?,?)",
                 (task_id, model, "queued", json.dumps(params), "", datetime.datetime.now().isoformat(), ""))
    conn.commit(); conn.close()

    threading.Thread(target=run_generation, args=(task_id, model, params), daemon=True).start()
    return jsonify({"task_id": task_id})

@app.route("/api/task/<task_id>")
def api_task(task_id):
    conn = get_conn()
    row = conn.execute("SELECT id,status,log,created_at,finished_at,returncode FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(dict(row))

@app.route("/api/tasks")
def api_tasks():
    conn = get_conn()
    rows = conn.execute("SELECT id,model,status,created_at,finished_at,returncode FROM tasks ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/tasks/<task_id>/log")
def api_task_log(task_id):
    conn = get_conn()
    row = conn.execute("SELECT log FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return jsonify({"log": row["log"] if row else ""})

@app.route("/api/pools/fetch-now", methods=["POST"])
def api_pool_fetch_now():
    data = request.get_json(force=True)
    region = data.get("region", "cn")
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from common.region import get_region_config
    cfg = get_region_config(region) or get_region_config("cn")
    lat_range = cfg["lat_range"]
    lon_range = cfg["lon_range"]
    # 随机生成若干目标坐标
    import random
    num_points = int(data.get("points", 3))
    coords = []
    for _ in range(num_points):
        lat = round(random.uniform(lat_range[0], lat_range[1]), 6)
        lon = round(random.uniform(lon_range[0], lon_range[1]), 6)
        coords.append([lat, lon])
    mnc = data.get("mnc", -1)
    if mnc in ("", None, "all", -1):
        mnc = -1
    else:
        mnc = int(mnc)
    # 统一落库文件名
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output = f"templates/cell_pools/pool_{region}_{ts}.json"
    params = {
        "coords": coords,
        "n": int(data.get("n", 10)),
        "mnc": mnc,
        "r": int(data.get("r", 1)),
        "sleep": float(data.get("sleep", 1.0)),
        "output": output,
        "append": bool(data.get("append", True)),
        "region": region,
    }
    task_id = uuid.uuid4().hex[:8]
    conn = get_conn()
    conn.execute("INSERT INTO tasks (id,model,status,params,log,created_at,output_path) VALUES (?,?,?,?,?,?,?)",
                 (task_id, "__pool_fetch__", "queued", json.dumps(params), "", datetime.datetime.now().isoformat(), ""))
    conn.commit(); conn.close()
    threading.Thread(target=run_pool_fetch, args=(task_id, params), daemon=True).start()
    return jsonify({"task_id": task_id, "coords": coords, "output": output})

@app.route("/api/files/tree")
def api_files_tree():
    # Only output directory, grouped by model (brand/model)
    # Only include generated device param files (JSON with 'env' key)
    base = os.path.join(ROOT, "output")
    tree = {}
    if os.path.exists(base):
        for brand in sorted(os.listdir(base)):
            brand_path = os.path.join(base, brand)
            if not os.path.isdir(brand_path):
                continue
            for model in sorted(os.listdir(brand_path)):
                model_path = os.path.join(brand_path, model)
                if not os.path.isdir(model_path):
                    continue
                files = []
                for root_, _, fs in os.walk(model_path):
                    for f in fs:
                        if not f.endswith(".json"):
                            continue
                        full = os.path.join(root_, f)
                        try:
                            d = json.load(open(full, encoding="utf-8"))
                            if not isinstance(d, dict) or "env" not in d:
                                continue
                        except Exception:
                            continue
                        rel = os.path.relpath(full, ROOT)
                        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M:%S")
                        files.append({"path": rel, "name": f, "mtime": mtime, "size": os.path.getsize(full)})
                key = f"{brand}/{model}"
                if files:
                    tree[key] = sorted(files, key=lambda x: x["path"])
    return jsonify(tree)

@app.route("/api/file/download")
def api_file_download():
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "path required"}), 400
    full = os.path.join(ROOT, path) if not os.path.isabs(path) else path
    if not os.path.exists(full) or os.path.isdir(full):
        return jsonify({"error": "not found"}), 404
    from flask import send_file
    return send_file(full, as_attachment=True, download_name=os.path.basename(full))

@app.route("/api/file/delete", methods=["POST"])
def api_file_delete():
    data = request.get_json(force=True)
    path = data.get("path")
    if not path:
        return jsonify({"error": "path required"}), 400
    full = os.path.join(ROOT, path) if not os.path.isabs(path) else path
    # safety: only allow under output/
    if not os.path.abspath(full).startswith(os.path.abspath(os.path.join(ROOT, "output"))):
        return jsonify({"error": "only files under output/ can be deleted"}), 403
    if not os.path.exists(full) or os.path.isdir(full):
        return jsonify({"error": "not found"}), 404
    try:
        os.remove(full)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/batches")
def api_batches():
    out = []
    base = os.path.join(ROOT, "output")
    if not os.path.exists(base):
        return jsonify(out)
    for root_, dirs, files in os.walk(base):
        if "manifest.json" in files:
            out.append({"path": os.path.relpath(root_, ROOT), "abs": root_})
    return jsonify(sorted(out, key=lambda x: x["path"], reverse=True))

@app.route("/api/validate", methods=["POST"])
def api_validate():
    data = request.get_json(force=True)
    path = data.get("path")
    full = os.path.join(ROOT, path) if path and not os.path.isabs(path) else path
    cmd = [PYTHON, os.path.join(ROOT, "tools", "validate.py"), full]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return jsonify({"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode})

@app.route("/api/crosscheck", methods=["POST"])
def api_crosscheck():
    data = request.get_json(force=True)
    path = data.get("path")
    full = os.path.join(ROOT, path) if path and not os.path.isabs(path) else path
    cmd = [PYTHON, os.path.join(ROOT, "tools", "cross_check.py"), full]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    return jsonify({"stdout": r.stdout, "stderr": r.stderr, "returncode": r.returncode})

@app.route("/api/file")
def api_file():
    path = request.args.get("path")
    full = os.path.join(ROOT, path) if path and not os.path.isabs(path) else path
    if not path or not os.path.exists(full) or os.path.isdir(full):
        return jsonify({"error": "not found"}), 404
    try:
        content = open(full, encoding="utf-8").read()
    except Exception:
        content = open(full, "rb").read().decode("utf-8", errors="replace")
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"content": content, "mtime": mtime, "size": os.path.getsize(full)})

# ---------- schedules ----------
@app.route("/api/schedules")
def api_schedules():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/schedules", methods=["POST"])
def api_schedule_create():
    data = request.get_json(force=True)
    name = data.get("name") or "schedule"
    model = data.get("model")
    trigger_type = data.get("trigger_type", "cron")  # cron / interval
    trigger_expr = data.get("trigger_expr", "0 2 * * *")
    params = data.get("params", {})
    sid = uuid.uuid4().hex[:8]
    conn = get_conn()
    conn.execute("INSERT INTO schedules (id,name,model,trigger_type,trigger_expr,params,enabled,last_run,next_run,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (sid, name, model, trigger_type, trigger_expr, json.dumps(params), 1, None, None, datetime.datetime.now().isoformat()))
    conn.commit(); conn.close()
    # register job
    try:
        if trigger_type == "cron":
            trigger = CronTrigger.from_crontab(trigger_expr)
        else:
            trigger = IntervalTrigger(minutes=int(trigger_expr))
        scheduler.add_job(execute_schedule, trigger, args=[sid], id=sid, replace_existing=True)
        job = scheduler.get_job(sid)
        if job and job.next_run_time:
            conn = get_conn()
            conn.execute("UPDATE schedules SET next_run=? WHERE id=?", (job.next_run_time.isoformat(), sid))
            conn.commit(); conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"id": sid})

@app.route("/api/schedules/<sid>", methods=["DELETE"])
def api_schedule_delete(sid):
    try:
        scheduler.remove_job(sid)
    except Exception:
        pass
    conn = get_conn()
    conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/schedules/<sid>/toggle", methods=["POST"])
def api_schedule_toggle(sid):
    conn = get_conn()
    row = conn.execute("SELECT enabled FROM schedules WHERE id=?", (sid,)).fetchone()
    if not row:
        conn.close(); return jsonify({"error": "not found"}), 404
    new_val = 0 if row["enabled"] else 1
    conn.execute("UPDATE schedules SET enabled=? WHERE id=?", (new_val, sid))
    conn.commit(); conn.close()
    if new_val == 1:
        conn = get_conn()
        r = conn.execute("SELECT trigger_type,trigger_expr FROM schedules WHERE id=?", (sid,)).fetchone()
        conn.close()
        try:
            if r["trigger_type"] == "cron":
                trigger = CronTrigger.from_crontab(r["trigger_expr"])
            else:
                trigger = IntervalTrigger(minutes=int(r["trigger_expr"]))
            scheduler.add_job(execute_schedule, trigger, args=[sid], id=sid, replace_existing=True)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    else:
        try:
            scheduler.remove_job(sid)
        except Exception:
            pass
    return jsonify({"enabled": new_val})

if __name__ == "__main__":
    load_schedules()
    scheduler.start()
    print(f"ROOT: {ROOT}")
    print("Open http://127.0.0.1:5000")
    try:
        app.run(host="0.0.0.0", port=5000, debug=False)
    finally:
        scheduler.shutdown()