"""Runs code against procedurally generated tests and classifies what went wrong.

Each test runs inside one `python -I runner.py` subprocess. If a single test
stops producing output for PER_TEST_TIMEOUT seconds (infinite loop), the process
is killed, that test is marked as a timeout, and a fresh process resumes from
the next test.
"""
import ast
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import uuid

from . import fileio
from .runner import dec, enc

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.py")
PER_TEST_TIMEOUT = 2.0
LOAD_TIMEOUT = 5.0
MAX_RESTARTS = 1

# category -> (label shown to the student, default point penalty)
CATEGORIES = {
    "syntax_error": ("Syntax error", 1.0),
    "indentation_error": ("Indentation error", 1.0),
    "missing_function": ("Function missing or misnamed", 1.0),
    "wrong_signature": ("Wrong number of parameters", 1.0),
    "load_error": ("Crash while loading file (top-level code)", 1.0),
    "name_error": ("NameError / undefined variable", 1.0),
    "type_error": ("TypeError", 1.0),
    "index_error": ("IndexError (out of range)", 1.0),
    "key_error": ("KeyError", 1.0),
    "zero_division": ("Division by zero", 1.0),
    "attribute_error": ("AttributeError", 1.0),
    "value_error": ("ValueError", 1.0),
    "recursion_error": ("Infinite recursion / missing base case", 1.5),
    "timeout": ("Infinite loop / too slow", 1.5),
    "missing_return": ("Returned None (missing return)", 1.0),
    "printed_instead_of_return": ("Printed instead of returning", 1.0),
    "wrong_type": ("Wrong return type", 1.0),
    "off_by_one": ("Off-by-one", 1.0),
    "edge_case": ("Fails edge cases (empty / boundary input)", 1.0),
    "wrong_answer": ("Wrong answer", 1.0),
    "constraint_violation": ("Broke a problem constraint", 2.0),
    "other_exception": ("Other runtime error", 1.0),
    # C-specific (see c_grader.py)
    "compile_error": ("Compile error", 1.0),
    "segfault": ("Crash: invalid memory access (segfault)", 1.5),
    "out_of_bounds": ("Out-of-bounds or uninitialized memory access", 1.5),
    "uninitialized_variable": ("Uninitialized variable", 1.0),
    "assignment_in_condition": ("= instead of == in a condition", 1.0),
    "format_specifier": ("printf/scanf format mismatch (missing & or wrong %)", 1.0),
    "integer_division": ("Integer division (lost the decimals)", 1.0),
    "output_format": ("Output format / spacing / precision mismatch", 0.5),
    "no_output": ("Printed nothing", 1.0),
    # file I/O (see fileio.py)
    "unchecked_fopen": ("Didn't handle a file that can't be opened (NULL from fopen)", 1.5),
    "wrong_filename": ("Opened the wrong file name", 1.0),
    "wrong_file_mode": ("Wrong file mode (\"r\" / \"w\" / \"a\")", 1.0),
    "file_not_created": ("Output file not written", 1.0),
    "file_not_closed": ("Forgot to fclose a file", 0.5),
    "feof_loop": ("while (!feof(...)) loop (processes the last value twice)", 1.0),
}

_EXC_MAP = {
    "SyntaxError": "syntax_error",
    "IndentationError": "indentation_error",
    "TabError": "indentation_error",
    "MissingFunction": "missing_function",
    "WrongSignature": "wrong_signature",
    "NameError": "name_error",
    "UnboundLocalError": "name_error",
    "TypeError": "type_error",
    "IndexError": "index_error",
    "KeyError": "key_error",
    "ZeroDivisionError": "zero_division",
    "AttributeError": "attribute_error",
    "ValueError": "value_error",
    "RecursionError": "recursion_error",
    "Timeout": "timeout",
}


# --------------------------------------------------------------------- running

def run_tests(code, spec, tests):
    """Like run_function over every test; file questions run each test in a fresh
    folder holding only that test's input files, and read back its output files."""
    func = spec["function"]
    if not fileio.has_files(spec):
        return run_function(code, func, [t["args"] for t in tests])
    outs = spec.get("output_files") or []
    results = []
    for t in tests:
        run = run_function(code, func, [t["args"]], t.get("files") or {}, outs)
        if run["load_error"]:
            return run
        results.append(run["results"][0])
    return {"load_error": None, "results": results}


def run_function(code, func, tests_args, files=None, output_files=()):
    """Run `func` from `code` on each arg list. Returns
    {"load_error": {...} | None, "results": [{"result"|"exc", "stdout", "files"?}, ...]}."""
    encoded = [[enc(a) for a in args] for args in tests_args]
    results = [None] * len(encoded)
    with tempfile.TemporaryDirectory(prefix="pp_", ignore_cleanup_errors=True) as tmp:
        path = os.path.join(tmp, "pp_solution", "solution.py")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)
        tmp = os.path.join(tmp, "work")
        fileio.prepare_dir(tmp, files)
        start, restarts = 0, 0
        while start < len(encoded):
            load_error, next_i = _run_batch(path, func, encoded, start, results, tmp)
            if load_error:
                return {"load_error": load_error, "results": []}
            if next_i >= len(encoded):
                break
            restarts += 1
            if restarts > MAX_RESTARTS:
                for i in range(next_i, len(encoded)):
                    results[i] = {"exc": {"type": "Timeout", "msg": "not run: too many timeouts"}}
                break
            start = next_i
        if output_files:
            got = fileio.read_outputs(tmp, output_files)
            for r in results:
                if r is not None:
                    r["files"] = got
    return {"load_error": None, "results": results}


def _run_batch(path, func, encoded, start, results, cwd):
    nonce = uuid.uuid4().hex
    proc = subprocess.Popen(
        [sys.executable, "-I", RUNNER, path, func, nonce],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=cwd, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    lines = queue.Queue()

    def pump():
        for line in proc.stdout:
            if line.startswith(nonce):
                lines.put(json.loads(line[len(nonce):]))
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    try:
        proc.stdin.write(json.dumps({"tests": encoded[start:]}))
        proc.stdin.close()
    except OSError:
        pass

    i = start
    loaded = False
    try:
        while i < len(encoded):
            try:
                msg = lines.get(timeout=PER_TEST_TIMEOUT if loaded else LOAD_TIMEOUT)
            except queue.Empty:
                if not loaded:
                    return {"type": "Timeout", "msg": "file took too long to load (infinite loop at top level?)",
                            "line": None}, i
                results[i] = {"exc": {"type": "Timeout",
                                      "msg": f"no result after {PER_TEST_TIMEOUT:.0f}s (infinite loop?)"},
                              "stdout": ""}
                return None, i + 1
            if msg is None:  # process died (e.g. hard crash) -- mark the rest
                for j in range(i, len(encoded)):
                    results[j] = {"exc": {"type": "Crash", "msg": "Python process crashed"}, "stdout": ""}
                return None, len(encoded)
            if "load_error" in msg:
                return msg["load_error"], i
            if msg.get("loaded"):
                loaded = True
                continue
            results[start + msg["i"]] = msg
            i = start + msg["i"] + 1
        return None, i
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


# ------------------------------------------------------------------ comparison

def same(expected, got):
    if isinstance(expected, bool) or isinstance(got, bool):
        return type(expected) is type(got) and expected == got
    if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
        return math.isclose(expected, got, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(expected, list) and isinstance(got, list):
        return len(expected) == len(got) and all(same(a, b) for a, b in zip(expected, got))
    if isinstance(expected, dict) and isinstance(got, dict):
        if "__dict__" in expected and "__dict__" in got:
            e = {json.dumps(k, sort_keys=True): v for k, v in expected["__dict__"]}
            g = {json.dumps(k, sort_keys=True): v for k, v in got["__dict__"]}
            return e.keys() == g.keys() and all(same(e[k], g[k]) for k in e)
        if expected.keys() != got.keys():
            return False
        return all(same(expected[k], got[k]) for k in expected)
    return expected == got


def show(v):
    """Encoded value -> Python-looking repr for display."""
    if isinstance(v, dict) and "__repr__" in v:
        return v["__repr__"]
    try:
        return repr(dec(v))
    except Exception:  # noqa: BLE001
        return json.dumps(v)


def call_str(func, args):
    return f"{func}({', '.join(repr(a) for a in args)})"


def _kind(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        for tag in ("__tuple__", "__set__", "__dict__"):
            if tag in v:
                return tag.strip("_")
        return v.get("__type__", "object")
    return type(v).__name__


def _off_by_one(e, g):
    if isinstance(e, (int, float)) and isinstance(g, (int, float)) and not isinstance(e, bool):
        return abs(e - g) == 1
    if isinstance(e, (list, str)) and isinstance(g, type(e)) and abs(len(e) - len(g)) == 1:
        short, long_ = (e, g) if len(e) < len(g) else (g, e)
        return long_[:len(short)] == short or long_[1:] == short
    return False


def classify_failure(test, expected, outcome):
    if outcome is None:
        return "other_exception"
    if "exc" in outcome:
        return _EXC_MAP.get(outcome["exc"]["type"], "other_exception")
    got = outcome["result"]
    if got is None and expected is not None:
        printed = outcome.get("stdout", "")
        if printed and (show(expected) in printed or str(dec(expected)) in printed):
            return "printed_instead_of_return"
        return "missing_return"
    if _kind(expected) != _kind(got):
        return "wrong_type"
    if _off_by_one(expected, got):
        return "off_by_one"
    if test.get("edge"):
        return "edge_case"
    return "wrong_answer"


# ----------------------------------------------------------------- constraints

def check_constraints(code, func, constraints):
    """Static checks (e.g. "must be recursive", "no loops"). Returns a list of messages."""
    if not constraints:
        return []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func), None)
    if fn is None:
        return []
    problems = []
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    called = {c.func.id for c in calls if isinstance(c.func, ast.Name)}
    called |= {c.func.attr for c in calls if isinstance(c.func, ast.Attribute)}
    if constraints.get("require_recursion") and func not in called:
        problems.append(f"`{func}` must be recursive (call itself)")
    if constraints.get("forbid_loops"):
        loops = (ast.For, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        if any(isinstance(n, loops) for n in ast.walk(fn)):
            problems.append("loops and comprehensions are not allowed")
    for name in constraints.get("forbid_builtins", []):
        if name in called:
            problems.append(f"`{name}` is not allowed")
    return problems


# --------------------------------------------------------------------- grading

def grade(code, spec, tests, visible=3):
    """tests: [{"args", "edge", "expected"}]. Returns
    {"frac", "passed", "total", "categories": {cat: n}, "load_error", "constraint_errors", "tests": [...]}."""
    if spec.get("language") == "c":
        from . import c_grader
        return c_grader.grade(code, spec, tests, visible)
    total = len(tests)
    report = {"frac": 0.0, "passed": 0, "total": total, "categories": {},
              "load_error": None, "constraint_errors": [], "tests": []}
    func = spec["function"]

    run = run_tests(code, spec, tests)
    if run["load_error"]:
        le = run["load_error"]
        report["load_error"] = le
        cat = _EXC_MAP.get(le["type"], "load_error")
        report["categories"][cat] = 1
        return report

    shown_failures = 0
    for idx, (t, outcome) in enumerate(zip(tests, run["results"])):
        ok = outcome is not None and "result" in outcome and same(t["expected"], outcome["result"])
        cat = None if ok else classify_failure(t, t["expected"], outcome)
        if t.get("expected_files") and outcome is not None:
            for name, exp in t["expected_files"].items():
                got = (outcome.get("files") or {}).get(name)
                if fileio.normalize(got) != fileio.normalize(exp):
                    if got is None and exp is not None:
                        ok, cat = False, "file_not_created"
                    elif ok:
                        ok, cat = False, "edge_case" if t.get("edge") else "wrong_answer"
                    break
        exc_type = (outcome or {}).get("exc", {}).get("type")
        if exc_type in ("FileNotFoundError", "PermissionError", "IsADirectoryError"):
            cat = "unchecked_fopen" if t.get("no_files") else "wrong_filename"
        elif exc_type == "UnsupportedOperation":  # e.g. writing to a file opened with "r"
            cat = "wrong_file_mode"
        elif not ok and t.get("no_files") and cat != "timeout":
            cat = "unchecked_fopen"
        if fileio.has_files(spec) and outcome and cat != "timeout":
            io_cats = fileio.io_problems([tuple(e) for e in outcome.get("io", [])], spec) - {"file_not_closed"}
            if "wrong_filename" in io_cats:
                ok, cat = False, "wrong_filename"  # fails even though Windows found the file
            elif not ok and "wrong_file_mode" in io_cats:
                cat = "wrong_file_mode"
        row = {"n": idx + 1, "ok": ok, "edge": t.get("edge", False)}
        if ok:
            report["passed"] += 1
        else:
            row["category"] = cat
            report["categories"][cat] = report["categories"].get(cat, 0) + 1
            # Like a real exam autograder: details for the first few failures,
            # the rest are reported as hidden tests.
            if shown_failures < visible:
                shown_failures += 1
                row["call"] = call_str(func, t["args"])
                row["expected"] = show(t["expected"])
                if outcome and "exc" in outcome:
                    e = outcome["exc"]
                    where = f" (line {e['line']})" if e.get("line") else ""
                    row["got"] = f"{e['type']}: {e['msg']}{where}"
                elif outcome:
                    row["got"] = show(outcome["result"])
                if outcome and outcome.get("stdout"):
                    row["stdout"] = outcome["stdout"][:500]
                if fileio.has_files(spec):
                    row["no_files"] = bool(t.get("no_files"))
                    row["files_in"] = t.get("files") or {}
                    row["expected_files"] = t.get("expected_files") or {}
                    row["got_files"] = (outcome or {}).get("files") or {}
            else:
                row["hidden"] = True
        report["tests"].append(row)

    report["frac"] = report["passed"] / total if total else 0.0
    violations = check_constraints(code, func, spec.get("constraints"))
    if violations:
        report["constraint_errors"] = violations
        report["categories"]["constraint_violation"] = len(violations)
        report["frac"] = 0.0
    return report


def expected_outputs(spec, tests):
    """Run the reference solution; sets t["expected"] (and t["expected_files"]).
    Raises ValueError if it fails on any test."""
    run = run_tests(spec["reference"], spec, tests)
    if run["load_error"]:
        le = run["load_error"]
        raise ValueError(f"reference solution failed to load: {le['type']}: {le['msg']}")
    for t, r in zip(tests, run["results"]):
        if r is None or "exc" in r:
            msg = r["exc"] if r else "no result"
            raise ValueError(f"reference solution failed on {call_str(spec['function'], t['args'])}: {msg}")
        t["expected"] = r["result"]
        if fileio.has_files(spec):
            t["expected_files"] = r.get("files") or {}
    return tests
