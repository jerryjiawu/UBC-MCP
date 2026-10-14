"""SQLite storage: practice sets, exam instances, attempts, the error log and
the penalty table. Shared by the web app and the MCP server (separate processes),
so every call opens its own short-lived connection.
"""
import json
import math
import os
import random
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager

from . import grader, problems

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PKG_DIR, "data")
SETS_DIR = os.path.join(PKG_DIR, "sets")
DB_PATH = os.path.join(DATA_DIR, "practice.db")
FORMAT = "ubc-practice/1"

DEFAULT_ADAPTIVE = {
    # every `every` past occurrences of an error adds `step` points to its
    # penalty, up to `cap`. Habitual mistakes get progressively more expensive.
    "step": 0.5,
    "every": 5,
    "cap": 3.0,
    # one bad attempt never costs more than this, however many errors it has
    "max_per_attempt": 3.0,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS sets (id TEXT PRIMARY KEY, title TEXT, data TEXT, created REAL);
CREATE TABLE IF NOT EXISTS instances (
    id INTEGER PRIMARY KEY, set_id TEXT, seed INTEGER, started REAL, finished REAL,
    time_limit_min INTEGER, max_attempts INTEGER);
CREATE TABLE IF NOT EXISTS instance_tests (instance_id INTEGER, qidx INTEGER, tests TEXT,
    PRIMARY KEY (instance_id, qidx));
CREATE TABLE IF NOT EXISTS drafts (instance_id INTEGER, qidx INTEGER, code TEXT, saved REAL,
    PRIMARY KEY (instance_id, qidx));
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY, instance_id INTEGER, qidx INTEGER, n INTEGER, code TEXT,
    frac REAL, raw_points REAL, penalty_before REAL, awarded REAL, deduction REAL,
    report TEXT, created REAL);
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY, attempt_id INTEGER, set_id TEXT, qidx INTEGER, topic TEXT,
    title TEXT, category TEXT, cost REAL, created REAL);
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ config

def _get_config(conn, key, default):
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def _set_config(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (key, json.dumps(value)))


def get_penalty_config():
    with db() as conn:
        base = {c: d for c, (_, d) in grader.CATEGORIES.items()}
        base.update(_get_config(conn, "penalties", {}))
        adaptive = dict(DEFAULT_ADAPTIVE, **_get_config(conn, "adaptive", {}))
        return base, adaptive


def set_penalty(category, points):
    if category not in grader.CATEGORIES:
        raise ValueError(f"unknown category {category!r}; choose from {', '.join(grader.CATEGORIES)}")
    with db() as conn:
        cur = _get_config(conn, "penalties", {})
        cur[category] = max(0.0, float(points))
        _set_config(conn, "penalties", cur)


def set_adaptive(**kw):
    with db() as conn:
        cur = dict(DEFAULT_ADAPTIVE, **_get_config(conn, "adaptive", {}))
        for k, v in kw.items():
            if k in DEFAULT_ADAPTIVE and v is not None:
                cur[k] = max(0.0, float(v)) if k != "every" else max(1, int(v))
        _set_config(conn, "adaptive", cur)
        return cur


def error_counts(conn=None):
    def q(c):
        return {r["category"]: r["n"] for r in
                c.execute("SELECT category, COUNT(*) n FROM errors GROUP BY category")}
    if conn is not None:
        return q(conn)
    with db() as c:
        return q(c)


def effective_penalty(category, base, adaptive, counts):
    b = base.get(category, 1.0)
    bonus = adaptive["step"] * math.floor(counts.get(category, 0) / adaptive["every"])
    return round(min(b + bonus, max(adaptive["cap"], b)), 2)


def penalty_table():
    base, adaptive = get_penalty_config()
    counts = error_counts()
    rows = []
    for cat, (label, _) in grader.CATEGORIES.items():
        rows.append({"category": cat, "label": label, "base": base[cat], "count": counts.get(cat, 0),
                     "effective": effective_penalty(cat, base, adaptive, counts)})
    rows.sort(key=lambda r: (-r["count"], r["category"]))
    return rows, adaptive


# -------------------------------------------------------------------- sets

def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "practice"


def save_set(title, questions, time_limit_min=50, max_attempts=5, description="", set_id=None):
    set_id = set_id or uuid.uuid4().hex[:8]
    languages = sorted({q.get("language", "python") for q in questions})
    data = {"format": FORMAT, "title": title, "description": description,
            "settings": {"time_limit_min": int(time_limit_min), "max_attempts": int(max_attempts),
                         "language": "+".join(languages) or "python"},
            "questions": questions}
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO sets VALUES (?, ?, ?, ?)",
                     (set_id, title, json.dumps(data), time.time()))
    path = export_set(set_id)
    return set_id, path


def get_set(set_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM sets WHERE id=?", (set_id,)).fetchone()
    if not row:
        raise KeyError(f"no practice set {set_id!r}")
    return json.loads(row["data"])


def list_sets():
    with db() as conn:
        rows = conn.execute("SELECT id, title, data, created FROM sets ORDER BY created DESC").fetchall()
        out = []
        for r in rows:
            data = json.loads(r["data"])
            inst = conn.execute("SELECT id, finished FROM instances WHERE set_id=? ORDER BY id DESC LIMIT 1",
                                (r["id"],)).fetchone()
            out.append({"id": r["id"], "title": r["title"], "created": r["created"],
                        "questions": len(data["questions"]),
                        "points": sum(q["points"] for q in data["questions"]),
                        "topics": sorted({q["topic"] for q in data["questions"]}),
                        "settings": data["settings"],
                        "open_instance": inst["id"] if inst and not inst["finished"] else None})
        return out


def add_question(set_id, spec):
    data = get_set(set_id)
    data["questions"].append(spec)
    save_set(data["title"], data["questions"], data["settings"]["time_limit_min"],
             data["settings"]["max_attempts"], data.get("description", ""), set_id)


def delete_set(set_id):
    with db() as conn:
        conn.execute("DELETE FROM sets WHERE id=?", (set_id,))


def export_set(set_id, out_dir=SETS_DIR):
    data = get_set(set_id)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{_slug(data['title'])}-{set_id}.ubcprac.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def import_set_data(data):
    """Imported sets contain reference solutions that run on this machine when
    tests are generated -- only import files from people you trust."""
    if data.get("format") != FORMAT:
        raise ValueError(f"not a {FORMAT} file")
    questions = [problems.normalize(dict(q)) for q in data["questions"]]
    s = data.get("settings", {})
    return save_set(data.get("title", "Imported set"), questions, s.get("time_limit_min", 50),
                    s.get("max_attempts", 5), data.get("description", ""))


# --------------------------------------------------------------- instances

def start_instance(set_id):
    data = get_set(set_id)
    seed = random.SystemRandom().randrange(1, 2**31)
    tests = [problems.build_tests(q, seed) for q in data["questions"]]
    s = data["settings"]
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO instances (set_id, seed, started, finished, time_limit_min, max_attempts) "
            "VALUES (?, ?, ?, NULL, ?, ?)",
            (set_id, seed, time.time(), s["time_limit_min"], s["max_attempts"]))
        iid = cur.lastrowid
        for i, t in enumerate(tests):
            conn.execute("INSERT INTO instance_tests VALUES (?, ?, ?)", (iid, i, json.dumps(t)))
    return iid


def get_instance(iid):
    with db() as conn:
        inst = conn.execute("SELECT * FROM instances WHERE id=?", (iid,)).fetchone()
        if not inst:
            raise KeyError(f"no instance {iid}")
        inst = dict(inst)
        if (not inst["finished"] and inst["time_limit_min"]
                and time.time() > inst["started"] + inst["time_limit_min"] * 60):
            inst["finished"] = inst["started"] + inst["time_limit_min"] * 60
            conn.execute("UPDATE instances SET finished=? WHERE id=?", (inst["finished"], iid))
    inst["set"] = get_set(inst["set_id"])
    inst["questions"] = [question_state(iid, i, q, inst["max_attempts"])
                         for i, q in enumerate(inst["set"]["questions"])]
    inst["total_points"] = sum(q["points"] for q in inst["set"]["questions"])
    inst["awarded"] = round(sum(q["awarded"] for q in inst["questions"]), 2)
    inst["remaining_s"] = (max(0, int(inst["started"] + inst["time_limit_min"] * 60 - time.time()))
                           if inst["time_limit_min"] and not inst["finished"] else None)
    return inst


def finish_instance(iid):
    with db() as conn:
        conn.execute("UPDATE instances SET finished=? WHERE id=? AND finished IS NULL", (time.time(), iid))


def question_state(iid, qidx, spec, max_attempts):
    with db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM attempts WHERE instance_id=? AND qidx=? ORDER BY n", (iid, qidx))]
        draft = conn.execute("SELECT code FROM drafts WHERE instance_id=? AND qidx=?",
                             (iid, qidx)).fetchone()
    for r in rows:
        r["report"] = json.loads(r["report"])
    awarded = max((r["awarded"] for r in rows), default=0.0)
    penalty = round(sum(r["deduction"] for r in rows), 2)
    complete = any(r["frac"] >= 1 for r in rows)
    used = len(rows)
    if complete:
        status = "complete"
    elif rows:
        status = "graded"
    elif draft:
        status = "saved"
    else:
        status = "unanswered"
    return {"idx": qidx, "spec": spec, "attempts": rows, "awarded": awarded,
            "penalty": penalty, "available": max(0.0, round(spec["points"] - penalty, 2)),
            "used": used, "max_attempts": max_attempts,
            "attempts_left": (max_attempts - used) if max_attempts else None,
            "locked": complete or bool(max_attempts and used >= max_attempts),
            "complete": complete, "status": status,
            "code": draft["code"] if draft else (rows[-1]["code"] if rows else spec["starter"])}


def save_draft(iid, qidx, code):
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO drafts VALUES (?, ?, ?, ?)", (iid, qidx, code, time.time()))


def submit(iid, qidx, code):
    """Grade one attempt, apply penalties, log errors. Returns the attempt row."""
    inst = get_instance(iid)
    if inst["finished"]:
        raise PermissionError("this assessment is closed")
    q = inst["questions"][qidx]
    if q["locked"]:
        raise PermissionError("no attempts left for this question")
    spec = q["spec"]
    save_draft(iid, qidx, code)

    with db() as conn:
        tests = json.loads(conn.execute("SELECT tests FROM instance_tests WHERE instance_id=? AND qidx=?",
                                        (iid, qidx)).fetchone()["tests"])
    report = grader.grade(code, spec, tests, spec.get("visible_failures", 3))

    base, adaptive = get_penalty_config()
    with db() as conn:
        counts = error_counts(conn)
        costs = {c: effective_penalty(c, base, adaptive, counts) for c in report["categories"]}
        deduction = 0.0 if report["frac"] >= 1 else round(min(sum(costs.values()),
                                                               adaptive["max_per_attempt"]), 2)
        raw = round(report["frac"] * spec["points"], 2)
        awarded = max(0.0, round(raw - q["penalty"], 2))
        report["costs"] = costs
        n = q["used"] + 1
        cur = conn.execute(
            "INSERT INTO attempts (instance_id, qidx, n, code, frac, raw_points, penalty_before, awarded, "
            "deduction, report, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (iid, qidx, n, code, report["frac"], raw, q["penalty"], awarded, deduction,
             json.dumps(report), time.time()))
        aid = cur.lastrowid
        for cat in report["categories"]:
            conn.execute("INSERT INTO errors (attempt_id, set_id, qidx, topic, title, category, cost, created) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (aid, inst["set_id"], qidx, spec["topic"], spec["title"], cat, costs[cat], time.time()))
    return {"attempt": n, "frac": report["frac"], "raw_points": raw, "penalty_before": q["penalty"],
            "awarded": awarded, "deduction": deduction, "report": report}


# ------------------------------------------------------------------- stats

def stats():
    with db() as conn:
        by_cat = error_counts(conn)
        by_topic = [dict(r) for r in conn.execute(
            "SELECT topic, COUNT(*) errors FROM errors GROUP BY topic ORDER BY errors DESC")]
        att_topic = {}
        for a in conn.execute("SELECT a.frac, s.data, a.qidx FROM attempts a "
                              "JOIN instances i ON a.instance_id=i.id JOIN sets s ON s.id=i.set_id"):
            topic = json.loads(a["data"])["questions"][a["qidx"]]["topic"]
            t = att_topic.setdefault(topic, {"attempts": 0, "perfect": 0})
            t["attempts"] += 1
            t["perfect"] += a["frac"] >= 1
        recent = [dict(r) for r in conn.execute(
            "SELECT a.id, a.instance_id, a.qidx, a.n, a.frac, a.awarded, a.deduction, a.created, "
            "s.title set_title, a.report FROM attempts a JOIN instances i ON a.instance_id=i.id "
            "JOIN sets s ON s.id=i.set_id ORDER BY a.id DESC LIMIT 40")]
        for r in recent:
            r["categories"] = list(json.loads(r.pop("report"))["categories"])
        totals = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(frac >= 1), 0) perfect FROM attempts").fetchone()
    for t in by_topic:
        a = att_topic.get(t["topic"], {"attempts": 0, "perfect": 0})
        t.update(a)
        t["error_rate"] = round(t["errors"] / a["attempts"], 2) if a["attempts"] else 0
    return {"by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
            "by_topic": by_topic, "recent": recent,
            "attempts": totals["n"], "perfect_attempts": totals["perfect"]}


def topic_weakness():
    """{topic: 0..1}, higher = more errors per attempt. Used to target practice."""
    rows = stats()["by_topic"]
    top = max((r["error_rate"] for r in rows), default=0)
    return {r["topic"]: (r["error_rate"] / top if top else 0) for r in rows}
