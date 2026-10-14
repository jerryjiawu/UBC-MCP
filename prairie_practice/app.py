"""PrairieTest/PrairieLearn exam UI for local practice sets.

    python -m prairie_practice.app          (http://127.0.0.1:5070)

The pages reuse PrairieLearn's own front end: its stylesheets (colors.css,
local.css, pageLayout.css, element CSS) and the pl-file-editor script are
vendored unmodified in static/pl/ (AGPL-3.0, see static/pl/LICENSE-PrairieLearn.txt),
and the templates reproduce the markup of PrairieLearn's student exam pages.

SECURITY: binds to 127.0.0.1 only and has no authentication. Submitted code and
imported reference solutions run as normal programs on this machine.
"""
import base64
import binascii
import datetime as dt
import html
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

if __package__ in (None, ""):  # allow `python prairie_practice/app.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "prairie_practice"

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from markupsafe import Markup

from prairie_practice import grader, store

PORT = int(os.getenv("PRAIRIE_PRACTICE_PORT", "5070"))
TZ = ZoneInfo(os.getenv("PRAIRIE_PRACTICE_TZ", "America/Vancouver"))
COURSE_LABEL = os.getenv("PRAIRIE_PRACTICE_COURSE", "APSC 160, Practice")

app = Flask(__name__)
app.secret_key = os.urandom(16)


# ----------------------------------------------------------------- filters

@app.template_filter("md")
def md(text):
    """Just enough markdown for problem prompts: `code`, **bold**, ```blocks```, paragraphs."""
    out = []
    for i, part in enumerate(re.split(r"```(?:python|c)?\n?", text)):
        if i % 2:
            out.append(f"<pre><code>{html.escape(part.rstrip())}</code></pre>")
            continue
        for para in re.split(r"\n\s*\n", part.strip()):
            if not para.strip():
                continue
            p = html.escape(" ".join(para.split()))
            p = re.sub(r"`([^`]+)`", r"<code>\1</code>", p)
            p = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", p)
            out.append(f"<p>{p}</p>")
    return Markup("".join(out))


@app.template_filter("pts")
def pts(v):
    """PrairieLearn's formatPoints: at most 2 decimals, no trailing zeros."""
    return f"{round(v or 0, 2):g}"


def _local(ts):
    return dt.datetime.fromtimestamp(ts, TZ)


@app.template_filter("friendly")
def friendly(ts):
    """PrairieLearn's formatDateFriendly, e.g. '21:05, Tue, Oct 13 (PDT)'."""
    d = _local(ts)
    return f"{d:%H:%M}, {d:%a}, {d:%b} {d.day} ({d.tzname()})"


@app.template_filter("fulldate")
def fulldate(ts):
    """PrairieLearn's formatDate, e.g. '2026-10-13 23:29:05-07 (PDT)'."""
    d = _local(ts)
    off = int(d.utcoffset().total_seconds() // 3600)
    return f"{d:%Y-%m-%d %H:%M:%S}{off:+03d} ({d.tzname()})"


@app.template_filter("ago")
def ago(ts):
    return _local(ts).strftime("%Y-%m-%d %H:%M")


@app.template_filter("b64")
def b64(text):
    return base64.b64encode((text or "").encode("utf-8")).decode("ascii")


@app.context_processor
def inject():
    return {"CATEGORY_LABELS": {k: v[0] for k, v in grader.CATEGORIES.items()},
            "COURSE_LABEL": COURSE_LABEL, "external_results": external_results}


# -------------------------------------------------------- grader view model

def external_results(attempt, spec):
    """Convert one attempt's report into the shape pl-external-grader-results renders."""
    r = attempt["report"]
    labels = {k: v[0] for k, v in grader.CATEGORIES.items()}
    msg = []
    if r.get("load_error"):
        le = r["load_error"]
        where = f" (line {le['line']})" if le.get("line") else ""
        msg.append(f"{le['type']}: {le['msg']}{where}")
        msg.append("No tests could run.")
    for c in r.get("constraint_errors", []):
        msg.append(f"Constraint violated: {c.replace('`', '')} -> score set to 0.")
    if r.get("categories"):
        msg.append("")
        msg.append("Errors detected:")
        costs = r.get("costs") or {}
        for cat, n in r["categories"].items():
            cost = f"  (-{pts(costs[cat])} pts)" if attempt["deduction"] and cat in costs else ""
            times = f" x{n}" if n > 1 else ""
            msg.append(f"  - {labels.get(cat, cat)}{times}{cost}")
    if attempt["deduction"]:
        msg.append("")
        msg.append(f"This attempt deducts {pts(attempt['deduction'])} point"
                   f"{'s' if attempt['deduction'] != 1 else ''} from the question's value for later attempts.")
    if attempt["penalty_before"]:
        msg.append(f"Awarded {pts(attempt['awarded'])} = {pts(attempt['raw_points'])} "
                   f"- {pts(attempt['penalty_before'])} penalty from earlier attempts.")

    tests = []
    for t in r.get("tests", []):
        name = f"Test {t['n']}" + (" (edge case)" if t.get("edge") else "")
        body = ""
        if not t["ok"]:
            if t.get("hidden"):
                body = f"Hidden test.\nError type: {labels.get(t.get('category'), t.get('category'))}"
            elif "stdin" in t:
                body = (f"Input:\n{t['stdin'].rstrip()}\n\nExpected output:\n{t['expected'].rstrip()}"
                        f"\n\nYour output:\n{(t.get('got') or '(nothing)').rstrip()}"
                        f"\n\nError type: {labels.get(t.get('category'), t.get('category'))}")
            else:
                body = (f"Call:     {t['call']}\nExpected: {t['expected']}\nGot:      {t.get('got', '')}"
                        + (f"\nPrinted:  {t['stdout']}" if t.get("stdout") else "")
                        + f"\n\nError type: {labels.get(t.get('category'), t.get('category'))}")
        tests.append({"index": t["n"], "name": name, "points": 1 if t["ok"] else 0, "max_points": 1,
                      "message": body,
                      "color": "#008c31" if t["ok"] else "#c72c1c",
                      "icon": "fa-check" if t["ok"] else "fa-times"})
    total = r.get("total") or 0
    return {"score": round(100 * attempt["frac"]), "points": r.get("passed", 0), "max_points": total,
            "color": "#008c31" if attempt["frac"] >= 1 else "#c72c1c",
            "message": "\n".join(msg).strip(), "output": (r.get("compiler_output") or "").strip(),
            "tests": tests}


# ------------------------------------------------------------------ routes

@app.route("/")
def home():
    return redirect(url_for("assessments"))


@app.route("/assessments")
def assessments():
    return render_template("home.html", sets=store.list_sets(), nav_page="assessments")


@app.post("/set/<set_id>/start")
def start(set_id):
    try:
        iid = store.start_instance(set_id)
    except (KeyError, ValueError, RuntimeError) as e:
        flash(str(e), "danger")
        return redirect(url_for("assessments"))
    return redirect(url_for("instance", iid=iid))


@app.route("/set/<set_id>/export")
def export(set_id):
    try:
        path = store.export_set(set_id)
    except KeyError:
        abort(404)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@app.post("/set/<set_id>/delete")
def delete(set_id):
    store.delete_set(set_id)
    return redirect(url_for("assessments"))


@app.post("/import")
def import_set():
    f = request.files.get("file")
    if not f:
        flash("Choose a .ubcprac.json file first.", "warning")
        return redirect(url_for("assessments"))
    try:
        store.import_set_data(json.load(f.stream))
        flash("Practice set imported.", "success")
    except (ValueError, KeyError, RuntimeError) as e:
        flash(f"Import failed: {e}", "danger")
    return redirect(url_for("assessments"))


def _instance_or_404(iid):
    try:
        return store.get_instance(iid)
    except KeyError:
        abort(404)


def _exam_label(inst):
    sets = [s["id"] for s in reversed(store.list_sets())]
    n = sets.index(inst["set_id"]) + 1 if inst["set_id"] in sets else 1
    return f"E{n}", n


@app.route("/instance/<int:iid>", methods=["GET", "POST"])
def instance(iid):
    if request.method == "POST":
        action = request.form.get("__action")
        if action == "grade":
            n = store.grade_saved(iid)
            flash(f"Graded {n} saved answer{'s' if n != 1 else ''}.", "info")
        elif action in ("finish", "timeLimitFinish"):
            store.finish_instance(iid)
            if action == "timeLimitFinish":
                return redirect(url_for("instance", iid=iid, time_expired=1))
        return redirect(url_for("instance", iid=iid))
    inst = _instance_or_404(iid)
    label, number = _exam_label(inst)
    saved = sum(1 for q in inst["questions"] if q["saved_pending"] and not q["locked"])
    return render_template("instance.html", inst=inst, exam_label=label, exam_number=number,
                           saved_answers=saved, nav_page="assessment_instance",
                           show_time_expired=bool(request.args.get("time_expired")))


@app.route("/instance/<int:iid>/time_remaining")
def time_remaining(iid):
    inst = _instance_or_404(iid)
    remaining = (inst["deadline"] - time.time()) if inst["deadline"] and not inst["finished"] else 0
    return jsonify({"serverRemainingMS": max(0, int(remaining * 1000)),
                    "serverTimeLimitMS": (inst["time_limit_min"] or 0) * 60000})


@app.route("/instance/<int:iid>/q/<int:qn>", methods=["GET", "POST"])
def question(iid, qn):
    if request.method == "POST":
        try:
            code = base64.b64decode(request.form.get("_file_editor", "")).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            abort(400)
        try:
            if request.form.get("__action") == "save":
                store.save_draft(iid, qn - 1, code)
            else:
                store.submit(iid, qn - 1, code)
        except PermissionError as e:
            flash(str(e), "warning")
        except (KeyError, IndexError):
            abort(404)
        return redirect(url_for("question", iid=iid, qn=qn))

    inst = _instance_or_404(iid)
    if not 1 <= qn <= len(inst["questions"]):
        abort(404)
    q = inst["questions"][qn - 1]
    label, number = _exam_label(inst)
    penalties, _ = store.penalty_table()
    return render_template("question.html", inst=inst, q=q, qn=qn, exam_label=label, exam_number=number,
                           closed=bool(inst["finished"] or q["locked"]),
                           is_c=q["spec"].get("language") == "c",
                           nav_page="assessment_instance",
                           penalties=[p for p in penalties if p["count"]][:6])


@app.route("/stats")
def stats():
    table, adaptive = store.penalty_table()
    return render_template("stats.html", s=store.stats(), table=table, adaptive=adaptive,
                           sets=store.list_sets(), nav_page="gradebook")


@app.post("/stats/penalties")
def update_penalties():
    for cat in grader.CATEGORIES:
        v = request.form.get(f"pen_{cat}")
        if v not in (None, ""):
            store.set_penalty(cat, float(v))
    store.set_adaptive(**{k: request.form.get(k) or None for k in store.DEFAULT_ADAPTIVE})
    flash("Penalty table updated. New values apply to future attempts.", "success")
    return redirect(url_for("stats"))


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/health")
def health():
    return {"ok": True, "app": "prairie-practice"}


def main():
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
