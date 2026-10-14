"""Subprocess side of the grader. Run as:

    python -I runner.py <code_file> <function_name> <nonce>

Reads {"tests": [[encoded args], ...]} from stdin *before* loading the student's
file (so a stray input() can't eat the tests), then prints one protocol line per
test, prefixed with <nonce> so student print() output can't be confused with it.

Values cross the process boundary via enc()/dec(), which preserve tuples, sets
and non-string dict keys that plain JSON would lose. grader.py imports these.
"""
import contextlib
import copy
import inspect
import io
import json
import math
import sys
import traceback

STDOUT_CAP = 4000


def enc(v):
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else {"__float__": repr(v)}
    if isinstance(v, list):
        return [enc(x) for x in v]
    if isinstance(v, tuple):
        return {"__tuple__": [enc(x) for x in v]}
    if isinstance(v, (set, frozenset)):
        return {"__set__": sorted((enc(x) for x in v), key=repr)}
    if isinstance(v, dict):
        return {"__dict__": [[enc(k), enc(x)] for k, x in v.items()]}
    return {"__repr__": repr(v)[:500], "__type__": type(v).__name__}


def dec(v):
    if isinstance(v, list):
        return [dec(x) for x in v]
    if isinstance(v, dict):
        if "__tuple__" in v:
            return tuple(dec(x) for x in v["__tuple__"])
        if "__set__" in v:
            return set(dec(x) for x in v["__set__"])
        if "__dict__" in v:
            return {_hashable(dec(k)): dec(x) for k, x in v["__dict__"]}
        if "__float__" in v:
            return float(v["__float__"])
    return v


def _hashable(k):
    return tuple(k) if isinstance(k, list) else k


def _student_line(tb):
    for frame in reversed(traceback.extract_tb(tb)):
        if frame.filename == "<student>":
            return frame.lineno
    return None


def main():
    code_file, func_name, nonce = sys.argv[1], sys.argv[2], sys.argv[3]
    real_out = sys.stdout
    payload = json.loads(sys.stdin.read())
    sys.stdin = io.StringIO("")

    def emit(obj):
        real_out.write(nonce + json.dumps(obj) + "\n")
        real_out.flush()

    with open(code_file, encoding="utf-8") as fh:
        src = fh.read()
    ns = {"__name__": "__student__"}
    buf = io.StringIO()
    try:
        code = compile(src, "<student>", "exec")
        with contextlib.redirect_stdout(buf):
            exec(code, ns)
    except SyntaxError as e:
        emit({"load_error": {"type": type(e).__name__, "msg": e.msg, "line": e.lineno}})
        return
    except BaseException as e:  # noqa: BLE001 -- report anything the student's top level raises
        emit({"load_error": {"type": type(e).__name__, "msg": str(e)[:300],
                             "line": _student_line(e.__traceback__)}})
        return

    fn = ns.get(func_name)
    if not callable(fn):
        emit({"load_error": {"type": "MissingFunction",
                             "msg": f"no function named '{func_name}' was defined", "line": None}})
        return
    emit({"loaded": True})

    for i, raw_args in enumerate(payload["tests"]):
        args = [dec(a) for a in raw_args]
        buf = io.StringIO()
        out = {"i": i}
        try:
            inspect.signature(fn).bind(*args)
        except TypeError as e:
            out["exc"] = {"type": "WrongSignature", "msg": str(e), "line": None}
            emit(out)
            continue
        except ValueError:
            pass  # builtins without signatures; just try calling
        try:
            with contextlib.redirect_stdout(buf):
                result = fn(*copy.deepcopy(args))
            out["result"] = enc(result)
        except BaseException as e:  # noqa: BLE001
            out["exc"] = {"type": type(e).__name__, "msg": str(e)[:300],
                          "line": _student_line(e.__traceback__)}
        out["stdout"] = buf.getvalue()[:STDOUT_CAP]
        emit(out)


if __name__ == "__main__":
    main()
