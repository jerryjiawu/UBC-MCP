"""PrairieLearn-style local exam app for practice sets.

    python -m prairie_practice.app          (http://127.0.0.1:5070)

SECURITY: binds to 127.0.0.1 only and has no authentication. Submitted code and
imported reference solutions run as normal Python on this machine.
"""
import html
import json
import os
import re
import sys
import time

if __package__ in (None, ""):  # allow `python prairie_practice/app.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "prairie_practice"

from markupsafe import Markup
from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from prairie_practice import grader, problems, store

PORT = int(os.getenv("PRAIRIE_PRACTICE_PORT", "5070"))

app = Flask(__name__)
app.secret_key = os.urandom(16)


@app.template_filter("md")
def md(text):
    """Just enough markdown for problem prompts: `code`, **bold**, ```blocks```, paragraphs."""
    out = []
    for i, part in enumerate(re.split(r"```(?:python)?\n?", text)):
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
    return f"{v:g}"


@app.template_filter("ago")
def ago(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


@app.context_processor
def inject():
    return {"CATEGORY_LABELS": {k: v[0] for k, v in grader.CATEGORIES.items()}}


# ------------------------------------------------------------------ routes

@app.route("/")
def home():
    return render_template("home.html", sets=store.list_sets())


@app.post("/set/<set_id>/start")
def start(set_id):
    try:
        iid = store.start_instance(set_id)
    except (KeyError, ValueError) as e:
        flash(str(e), "danger")
        return redirect(url_for("home"))
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
    return redirect(url_for("home"))


@app.post("/import")
def import_set():
    f = request.files.get("file")
    if not f:
        flash("Choose a .ubcprac.json file first.", "warning")
        return redirect(url_for("home"))
    try:
        set_id, _ = store.import_set_data(json.load(f.stream))
        flash("Practice set imported.", "success")
    except (ValueError, KeyError) as e:
        flash(f"Import failed: {e}", "danger")
    return redirect(url_for("home"))


def _instance_or_404(iid):
    try:
        return store.get_instance(iid)
    except KeyError:
        abort(404)


@app.route("/instance/<int:iid>")
def instance(iid):
    return render_template("instance.html", inst=_instance_or_404(iid))


@app.post("/instance/<int:iid>/finish")
def finish(iid):
    store.finish_instance(iid)
    return redirect(url_for("instance", iid=iid))


@app.route("/instance/<int:iid>/q/<int:qn>")
def question(iid, qn):
    inst = _instance_or_404(iid)
    if not 1 <= qn <= len(inst["questions"]):
        abort(404)
    q = inst["questions"][qn - 1]
    penalties, adaptive = store.penalty_table()
    return render_template("question.html", inst=inst, q=q, qn=qn,
                           penalties=[p for p in penalties if p["count"]][:6])


@app.post("/instance/<int:iid>/q/<int:qn>/submit")
def submit(iid, qn):
    code = request.form.get("code", "")
    try:
        if request.form.get("action") == "save":
            store.save_draft(iid, qn - 1, code)
            flash("Saved (not graded).", "info")
        else:
            store.submit(iid, qn - 1, code)
    except PermissionError as e:
        flash(str(e), "warning")
    except (KeyError, IndexError):
        abort(404)
    return redirect(url_for("question", iid=iid, qn=qn) + "#submissions")


@app.route("/stats")
def stats():
    table, adaptive = store.penalty_table()
    return render_template("stats.html", s=store.stats(), table=table, adaptive=adaptive)


@app.post("/stats/penalties")
def update_penalties():
    for cat in grader.CATEGORIES:
        v = request.form.get(f"pen_{cat}")
        if v not in (None, ""):
            store.set_penalty(cat, float(v))
    store.set_adaptive(**{k: request.form.get(k) or None for k in store.DEFAULT_ADAPTIVE})
    flash("Penalty table updated. New values apply to future attempts.", "success")
    return redirect(url_for("stats"))


@app.route("/health")
def health():
    return {"ok": True, "app": "prairie-practice"}


def main():
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
