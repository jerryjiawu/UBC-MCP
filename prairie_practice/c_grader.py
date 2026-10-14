"""C support (APSC 160 style), compiled with zig's bundled clang (`pip install ziglang`).

Two kinds of C question:

* "function": the student writes one function with a given prototype. A
  generated harness `#include`s their file (their own `main`, if any, is renamed
  away), calls the function once per test and prints the return value, every
  pointer out-parameter and every non-const array as a JSON line.
  Each test runs twice with different "canary" values placed just past the end of
  every array: if the two runs disagree, or a canary was overwritten, the code
  touched memory it shouldn't (out-of-bounds index / uninitialized memory).

* "program": the student writes a whole program with `main` that reads stdin
  (scanf) and prints to stdout. Each test is a separate run; output is compared
  line by line (trailing whitespace ignored).

Compiler warnings (-Wall) that match classic beginner bugs -- `=` in a condition,
uninitialized variables, missing return, scanf without `&` -- are added as error
categories when the attempt fails.
"""
import json
import math
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import uuid

PER_TEST_TIMEOUT = 2.0
MAX_RESTARTS = 1
COMPILE_TIMEOUT = 120  # the very first compile builds zig's libc cache (~30s)
CANARY = (104729, -7919)  # values written past the end of int arrays, per run
DOUBLE_CANARY = (104729.5, -7919.25)
CHAR_CANARY = ("#", "@")
OUT_SENTINEL = -12345  # initial value of pointer out-parameters

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CRASH_CODES = {
    0xC0000005: ("segfault", "Crash: invalid memory access (segmentation fault)"),
    0xC00000FD: ("recursion_error", "Crash: stack overflow (infinite recursion?)"),
    0xC0000094: ("zero_division", "Crash: integer division by zero"),
    0xC0000409: ("out_of_bounds", "Crash: stack buffer overrun"),
    0xC000001D: ("segfault", "Crash: illegal instruction"),
    0xC0000374: ("segfault", "Crash: heap corruption"),
}

# compiler warning regex -> category (only counted when the attempt fails)
WARNING_CATEGORIES = [
    (r"using the result of an assignment as a condition", "assignment_in_condition"),
    (r"is uninitialized when used|may be uninitialized|sometimes-uninitialized", "uninitialized_variable"),
    (r"does not return a value", "missing_return"),
    (r"format specifies type|-Wformat", "format_specifier"),
]

ERROR_CATEGORIES = [
    (r"conflicting types for|too (many|few) arguments to function call", "wrong_signature"),
    (r"undefined symbol|undefined reference", "missing_function"),
    (r"undeclared identifier|call to undeclared (library )?function|implicit declaration", "name_error"),
]


class CompilerMissing(RuntimeError):
    pass


def compiler_available():
    try:
        import ziglang  # noqa: F401
        return True
    except ImportError:
        return False


# --------------------------------------------------------------- compiling

def compile_c(sources, exe, cwd):
    """Returns (ok, diagnostics_text). Diagnostics have temp paths stripped."""
    if not compiler_available():
        raise CompilerMissing("C questions need the zig compiler: run `pip install ziglang` in the app's venv")
    cmd = [sys.executable, "-m", "ziglang", "cc", "-std=c11", "-O0", "-g0", "-Wall",
           "-Wno-unused-variable", "-Wno-unused-function", "-Wno-unused-but-set-variable",
           "-fno-sanitize=all", "-fno-caret-diagnostics", "-o", exe] + sources
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=COMPILE_TIMEOUT, creationflags=_NOWIN)
    except subprocess.TimeoutExpired:
        return False, "compiler timed out"
    text = (r.stdout + r.stderr).replace(cwd + os.sep, "").replace(cwd.replace("\\", "/") + "/", "")
    # zig prints a trailing build summary on failure; keep only clang's lines
    # drop zig driver noise (its build summary, "argument unused" warnings); keep clang's lines
    lines = [ln for ln in text.splitlines()
             if not ln.startswith(("error: the following command", "error: unable to", "    ", "zig: "))
             or "solution.c" in ln]
    return r.returncode == 0 and os.path.exists(os.path.join(cwd, exe)), "\n".join(lines).strip()


def diagnostics(text, filename="solution.c"):
    """[(kind, line, message)] for diagnostics in the student's file."""
    out = []
    for m in re.finditer(r"^(?:.*?)" + re.escape(filename) + r":(\d+):\d+: (error|warning): (.*)$",
                         text, re.M):
        out.append((m.group(2), int(m.group(1)), m.group(3)))
    for m in re.finditer(r"^(?:ld\.lld|lld-link|error): (.*undefined symbol.*)$", text, re.M):
        out.append(("error", None, m.group(1)))
    return out


def _crash(code):
    code &= 0xFFFFFFFF
    if code in CRASH_CODES:
        return CRASH_CODES[code]
    if code >= 0xC0000000:
        return "segfault", f"Crash (exception 0x{code:08X})"
    return None


# ---------------------------------------------------------------- C values

def c_literal(v, ctype):
    base = ctype.replace("const", "").strip()
    if base.startswith("double"):
        return repr(float(v))
    if base.startswith("char") and not base.endswith("[]"):
        return "'" + _c_escape(v) + "'"
    if isinstance(v, str):
        return '"' + _c_escape(v) + '"'
    if isinstance(v, bool):
        return "1" if v else "0"
    return str(int(v))


def _c_escape(s):
    return "".join({"\\": "\\\\", '"': '\\"', "'": "\\'", "\n": "\\n", "\t": "\\t"}.get(c, c) for c in s)


def _base(t):
    """'const int[]' -> 'int', 'double*' -> 'double', 'int[][5]' -> 'int'."""
    return re.sub(r"const|\[.*|\*", "", t).strip()


def _cols(t):
    m = re.search(r"\[\]\[(\d+)\]", t)
    return int(m.group(1)) if m else None


def prototype(spec):
    parts = []
    for p in spec["params"]:
        t = p["type"]
        if "[" in t:
            dims = t[t.index("["):]
            parts.append(f"{t[:t.index('[')].strip()} {p['name']}{dims}")
        elif t.endswith("*"):
            parts.append(f"{t[:-1].strip()} *{p['name']}")
        else:
            parts.append(f"{t} {p['name']}")
    return f"{spec.get('returns', 'void')} {spec['function']}({', '.join(parts) or 'void'})"


def input_params(spec):
    """Params whose values come from the DSL (the test 'args', in order)."""
    return [p for p in spec["params"] if p.get("input")]


# ----------------------------------------------------------------- harness

_PRELUDE = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static void pp_d(double x) {
    if (isnan(x)) printf("\"nan\"");
    else if (isinf(x)) printf(x > 0 ? "\"inf\"" : "\"-inf\"");
    else printf("%.15g", x);
}
static void pp_s(const char *s, int cap) {
    putchar('"');
    for (int i = 0; i < cap && s[i]; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') printf("\\%c", c);
        else if (c < 32 || c > 126) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}
static void pp_c(char c) { char b[2] = {c, 0}; pp_s(b, 1); }
"""


def build_harness(spec, tests, nonce):
    ret = spec.get("returns", "void")
    params = spec["params"]
    by_name = {p["name"]: p for p in params}
    lines = [_PRELUDE, prototype(spec) + ";",
             "#define main pp_student_main", '#include "solution.c"', "#undef main", ""]

    for ti, t in enumerate(tests):
        vals = {p["name"]: v for p, v in zip(input_params(spec), t["args"])}
        body, call_args, report, canary_checks = [], [], [], []
        for p in params:
            name, typ = p["name"], p["type"]
            base, const = _base(typ), "const" in typ
            if "[" in typ and _cols(typ):  # 2D array
                cols = _cols(typ)
                grid = vals.get(name, [])
                rows = len(grid)
                init = ", ".join("{" + ", ".join(c_literal(x, base) for x in row) + "}" for row in grid)
                body.append(f"{base} {name}[{rows + 1}][{cols}] = {{{init}{', ' if init else ''}{{0}}}};")
                body.append(f"for (int k = 0; k < {cols}; k++) {name}[{rows}][k] = "
                            f"({base})(v ? {CANARY[1]} : {CANARY[0]});")
                canary_checks.append(f"for (int k = 0; k < {cols}; k++) if ({name}[{rows}][k] != "
                                     f"({base})(v ? {CANARY[1]} : {CANARY[0]})) ok = 0;")
                if not const:
                    report.append((name, f"printf(\"[\"); for (int r = 0; r < {rows}; r++) {{ if (r) printf(\",\"); "
                                         f"printf(\"[\"); for (int k = 0; k < {cols}; k++) {{ if (k) printf(\",\"); "
                                         + _print_scalar(base, f"{name}[r][k]") + " } printf(\"]\"); } printf(\"]\");"))
                call_args.append(name)
            elif typ.endswith("[]") and base == "char":  # string buffer
                s = vals.get(name, "")
                cap = max(len(s) + 1, int(p.get("capacity", 0))) + 4
                body.append(f"char {name}[{cap}]; memset({name}, v ? '{CHAR_CANARY[1]}' : '{CHAR_CANARY[0]}', {cap}); "
                            f"memcpy({name}, \"{_c_escape(s)}\", {len(s) + 1});")
                canary_checks.append(f"if ({name}[{cap - 1}] != (v ? '{CHAR_CANARY[1]}' : '{CHAR_CANARY[0]}')) ok = 0;")
                if not const:
                    report.append((name, f"pp_s({name}, {cap - 4});"))
                call_args.append(name)
            elif typ.endswith("[]"):  # 1D array, input or output
                if p.get("input"):
                    arr = vals[name]
                elif p.get("out_len"):
                    arr = [OUT_SENTINEL] * len(vals[p["out_len"]])
                else:
                    arr = [OUT_SENTINEL] * int(p.get("length", 0))
                n = len(arr)
                can = DOUBLE_CANARY if base == "double" else CANARY
                init = ", ".join(c_literal(x, base) for x in arr)
                body.append(f"{base} {name}[{n + 2}] = {{{init}{', ' if init else ''}0}};")
                body.append(f"{name}[{n}] = {name}[{n + 1}] = v ? {can[1]} : {can[0]};")
                canary_checks.append(f"if ({name}[{n}] != (v ? {can[1]} : {can[0]}) || "
                                     f"{name}[{n + 1}] != (v ? {can[1]} : {can[0]})) ok = 0;")
                if not const:
                    report.append((name, f"printf(\"[\"); for (int k = 0; k < {n}; k++) {{ if (k) printf(\",\"); "
                                         + _print_scalar(base, f"{name}[k]") + " } printf(\"]\");"))
                call_args.append(name)
            elif typ.endswith("*"):  # pointer: out-param (or in/out if it has an input)
                init = c_literal(vals[name], base) if name in vals else str(OUT_SENTINEL)
                body.append(f"{base} {name} = {init};")
                report.append((name, _print_scalar(base, name)))
                call_args.append("&" + name)
            else:  # scalar
                if "size_of" in p:
                    val = str(len(vals[p["size_of"]]))
                elif "rows_of" in p:
                    val = str(len(vals[p["rows_of"]]))
                else:
                    val = c_literal(vals[name], base)
                body.append(f"{base} {name} = {val};")
                call_args.append(name)

        call = f"{spec['function']}({', '.join(call_args)})"
        if ret == "void":
            body.append(call + ";")
        else:
            body.append(f"{ret} pp_ret = {call};")
        out = [f'printf("\\n{nonce}R {ti} %d ", v); printf("{{");']
        first = True
        if ret != "void":
            out.append('printf("\\"return\\":"); ' + _print_scalar(ret, "pp_ret"))
            first = False
        for name, printer in report:
            out.append(f'printf("{"" if first else ","}\\"{name}\\":"); {printer}')
            first = False
        out.append(f'printf("{"" if first else ","}\\"__canary_ok\\":%d}}\\n", ok);')
        lines.append(f"static void pp_t{ti}(int v) {{")
        lines += ["    " + b for b in body]
        lines.append("    int ok = 1;")
        lines += ["    " + c for c in canary_checks]
        lines += ["    " + o for o in out]
        lines.append("}")

    lines.append(f"static void (*pp_tests[])(int) = {{{', '.join(f'pp_t{i}' for i in range(len(tests))) or '0'}}};")
    lines.append(r"""
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    int start = argc > 1 ? atoi(argv[1]) : 0;
    for (int i = start; i < %d; i++) {
        printf("\n%sB %%d\n", i);
        pp_tests[i](0);
        pp_tests[i](1);
    }
    printf("\n%sDONE\n");
    return 0;
}""" % (len(tests), nonce, nonce))
    return "\n".join(lines)


def _print_scalar(ctype, expr):
    base = _base(ctype)
    if base == "double" or base == "float":
        return f"pp_d({expr});"
    if base == "char":
        return f"pp_c({expr});"
    return f'printf("%lld", (long long)({expr}));'


# ------------------------------------------------------------------ running

def run_function_tests(code, spec, tests):
    """-> {"compile_ok", "compiler_output", "results": [{"r0", "r1", "stdout"} | {"crash"} | {"timeout"}]}"""
    nonce = "PP" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="ppc_") as tmp:
        with open(os.path.join(tmp, "solution.c"), "w", encoding="utf-8") as fh:
            fh.write(code)
        with open(os.path.join(tmp, "harness.c"), "w", encoding="utf-8") as fh:
            fh.write(build_harness(spec, tests, nonce))
        ok, diag = compile_c(["harness.c"], "harness.exe", tmp)
        if not ok:
            return {"compile_ok": False, "compiler_output": diag, "results": []}
        exe = os.path.join(tmp, "harness.exe")
        results = [None] * len(tests)
        start, timeouts = 0, 0
        while start < len(tests):
            nxt, timed_out = _run_harness(exe, nonce, start, len(tests), results, tmp)
            if nxt >= len(tests):
                break
            # crashes just restart at the next test; timeouts cost 2s each, so cap them
            timeouts += timed_out
            if timeouts > MAX_RESTARTS:
                for i in range(nxt, len(tests)):
                    results[i] = results[i] or {"timeout": True, "msg": "not run: too many timeouts"}
                break
            start = nxt
        return {"compile_ok": True, "compiler_output": diag, "results": results}


def _run_harness(exe, nonce, start, total, results, cwd):
    proc = subprocess.Popen([exe, str(start)], cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, creationflags=_NOWIN)
    q = queue.Queue()

    def pump():
        for raw in proc.stdout:
            q.put(raw.decode("utf-8", "replace").replace("\r\n", "\n"))
        q.put(None)

    threading.Thread(target=pump, daemon=True).start()
    cur, printed = None, []
    try:
        while True:
            try:
                line = q.get(timeout=PER_TEST_TIMEOUT)
            except queue.Empty:
                i = cur if cur is not None else start
                results[i] = {"timeout": True, "stdout": "".join(printed)[:2000]}
                return i + 1, True
            if line is None:  # process ended before printing DONE
                proc.wait()
                if cur is not None and "r1" not in (results[cur] or {}):
                    crash = _crash(proc.returncode) or ("other_exception", f"exited with code {proc.returncode}")
                    results[cur] = {"crash": crash[0], "msg": crash[1], "stdout": "".join(printed)[:2000]}
                    return cur + 1, False
                return total, False
            if line.startswith(nonce + "B "):
                cur, printed = int(line.split()[1]), []
                results[cur] = None
            elif line.startswith(nonce + "R "):
                _, i, v, payload = line.rstrip("\n").split(" ", 3)
                r = results[int(i)] or {}
                r[f"r{v}"] = json.loads(payload)
                if v == "1":
                    r["stdout"] = "".join(printed).strip("\n")[:2000]
                printed = []
                results[int(i)] = r
            elif line.startswith(nonce + "DONE"):
                return total, False
            else:
                printed.append(line)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()


_UNBUFFER = """#include <stdio.h>
__attribute__((constructor)) static void pp_unbuffer(void) { setvbuf(stdout, NULL, _IONBF, 0); }
"""


def run_program_tests(code, stdins):
    """-> {"compile_ok", "compiler_output", "results": [{"stdout", "crash"?, "timeout"?}]}"""
    with tempfile.TemporaryDirectory(prefix="ppc_") as tmp:
        with open(os.path.join(tmp, "solution.c"), "w", encoding="utf-8") as fh:
            fh.write(code)
        with open(os.path.join(tmp, "pp_unbuffer.c"), "w", encoding="utf-8") as fh:
            fh.write(_UNBUFFER)
        ok, diag = compile_c(["solution.c", "pp_unbuffer.c"], "solution.exe", tmp)
        if not ok:
            return {"compile_ok": False, "compiler_output": diag, "results": []}
        exe = os.path.join(tmp, "solution.exe")
        results = []
        timeouts = 0
        for stdin in stdins:
            if timeouts > MAX_RESTARTS:
                results.append({"timeout": True, "stdout": "", "msg": "not run: too many timeouts"})
                continue
            try:
                r = subprocess.run([exe], cwd=tmp, input=stdin.encode(), capture_output=True,
                                   timeout=PER_TEST_TIMEOUT, creationflags=_NOWIN)
                res = {"stdout": r.stdout.decode("utf-8", "replace").replace("\r\n", "\n")[:5000]}
                crash = _crash(r.returncode)
                if crash:
                    res["crash"], res["msg"] = crash
                results.append(res)
            except subprocess.TimeoutExpired as e:
                timeouts += 1
                results.append({"timeout": True,
                                "stdout": (e.stdout or b"").decode("utf-8", "replace").replace("\r\n", "\n")[:2000]})
        return {"compile_ok": True, "compiler_output": diag, "results": results}


# --------------------------------------------------------------- expected

def render_stdin(spec, args):
    vals = {name: v for name, v in zip(spec["inputs"], args)}

    def fmt(v):
        if isinstance(v, list):
            if v and isinstance(v[0], list):
                return "\n".join(" ".join(fmt(x) for x in row) for row in v)
            return " ".join(fmt(x) for x in v)
        if isinstance(v, float):
            return repr(v)
        return str(v)

    def sub(m):
        key = m.group(1)
        if key.startswith("len:"):
            return str(len(vals[key[4:]]))
        return fmt(vals[key])

    return re.sub(r"\{([a-zA-Z_:][a-zA-Z0-9_:]*)\}", sub, spec["stdin"])


def expected_outputs(spec, tests):
    if spec.get("kind") == "program":
        stdins = [render_stdin(spec, t["args"]) for t in tests]
        run = run_program_tests(spec["reference"], stdins)
        if not run["compile_ok"]:
            raise ValueError("reference solution failed to compile:\n" + run["compiler_output"][:1500])
        out = []
        for stdin, r in zip(stdins, run["results"]):
            if r.get("crash") or r.get("timeout"):
                raise ValueError(f"reference program failed on input {stdin!r}: {r.get('msg', 'timeout')}")
            out.append(r["stdout"])
        return out, stdins
    run = run_function_tests(spec["reference"], spec, tests)
    if not run["compile_ok"]:
        raise ValueError("reference solution failed to compile:\n" + run["compiler_output"][:1500])
    out = []
    for t, r in zip(tests, run["results"]):
        if not r or "r0" not in r:
            raise ValueError(f"reference solution failed on {call_str(spec, t['args'])}: "
                             f"{(r or {}).get('msg', 'timeout')}")
        if r["r0"] != r["r1"] or not r["r0"].get("__canary_ok", 1):
            raise ValueError(f"reference solution reads/writes out of bounds on {call_str(spec, t['args'])}")
        out.append({k: v for k, v in r["r0"].items() if k != "__canary_ok"})
    return out, None


# ---------------------------------------------------------------- display

def _show_val(v, ctype):
    base = _base(ctype)
    if isinstance(v, list):
        return "{" + ", ".join(_show_val(x, ctype) for x in v) + "}"
    if base in ("double", "float") and isinstance(v, (int, float)):
        return f"{float(v):.6g}" if abs(v) < 1e15 else repr(v)
    if base == "char" and "[" not in ctype:
        return "'" + str(v) + "'"
    if isinstance(v, str):
        return json.dumps(v)
    return str(v)


def call_str(spec, args):
    vals = {p["name"]: v for p, v in zip(input_params(spec), args)}
    parts, setup = [], []
    for p in spec["params"]:
        if p["name"] in vals and p["type"].endswith("*"):  # in/out pointer
            setup.append(f"{p['name']} = {_show_val(vals[p['name']], p['type'])}")
            parts.append("&" + p["name"])
        elif p["name"] in vals:
            parts.append(_show_val(vals[p["name"]], p["type"]))
        elif "size_of" in p:
            parts.append(str(len(vals[p["size_of"]])))
        elif "rows_of" in p:
            parts.append(str(len(vals[p["rows_of"]])))
        elif p["type"].endswith("*"):
            parts.append("&" + p["name"])
        else:
            parts.append(p["name"])
    call = f"{spec['function']}({', '.join(parts)})"
    return f"{', '.join(setup)}; {call}" if setup else call


def show_result(spec, result):
    types = {p["name"]: p["type"] for p in spec["params"]}
    bits = []
    for k, v in result.items():
        if k == "__canary_ok":
            continue
        if k == "return":
            bits.append(f"returns {_show_val(v, spec.get('returns', 'int'))}")
        else:
            prefix = "*" if types.get(k, "").endswith("*") else ""
            shown = "(never set)" if v == OUT_SENTINEL and prefix else _show_val(v, types.get(k, "int"))
            bits.append(f"{prefix}{k} = {shown}")
    return "; ".join(bits) or "(void)"


# ---------------------------------------------------------------- compare

def _close(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
    return a == b


def same_function(expected, got):
    return expected.keys() <= got.keys() and all(_close(expected[k], got[k]) for k in expected)


def normalize_output(s):
    lines = [ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _shape(text):
    """Output with numbers masked and whitespace/case ignored."""
    return "".join(_NUM.sub("#", text).split()).lower()


def classify_program_mismatch(expected, got, edge):
    exp_lines, got_lines = expected.split("\n"), got.split("\n") if got else []
    if len(exp_lines) >= 2 and got_lines in (exp_lines[:-1], exp_lines[1:]):
        return "off_by_one"  # one line too few (loop ran one time too few)
    if got_lines and exp_lines in (got_lines[:-1], got_lines[1:]):
        return "off_by_one"  # one line too many
    if not got.strip():
        return "no_output"
    if "".join(expected.split()).lower() == "".join(got.split()).lower():
        return "output_format"
    en, gn = _NUM.findall(expected), _NUM.findall(got)
    if _shape(expected) == _shape(got) and len(en) == len(gn):
        diffs = [(float(a), float(b), a, b) for a, b in zip(en, gn) if a != b]
        if all(math.isclose(a, b, abs_tol=0.051) for a, b, _, _ in diffs):
            return "output_format"  # precision / rounding (e.g. %.2f vs %f)
        if all("." in sa and b == math.trunc(b) and abs(a - b) < 1 for a, b, sa, _ in diffs):
            return "integer_division"
        if all(abs(a - b) == 1 for a, b, _, _ in diffs):
            return "off_by_one"
    return "edge_case" if edge else "wrong_answer"


def classify_function_mismatch(spec, expected, got, edge):
    ret = spec.get("returns", "void")
    for k, e in expected.items():
        g = got.get(k)
        if _close(e, g):
            continue
        typ = ret if k == "return" else next((p["type"] for p in spec["params"] if p["name"] == k), "int")
        if g == OUT_SENTINEL and typ.endswith("*"):
            return "wrong_answer"
        if (_base(typ) == "double" and isinstance(e, (int, float)) and isinstance(g, (int, float))
                and e != math.trunc(e) and g == math.trunc(g) and abs(e - g) < 1):
            return "integer_division"
        if isinstance(e, (int, float)) and isinstance(g, (int, float)) and abs(e - g) == 1:
            return "off_by_one"
        if (isinstance(e, list) and isinstance(g, list) and len(e) == len(g) >= 2
                and (e[1:] == g[:-1] or e[:-1] == g[1:])):
            return "off_by_one"  # shifted by one position
    return "edge_case" if edge else "wrong_answer"


# ------------------------------------------------------------ constraints

def _strip_comments_strings(code):
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', code)


def _function_body(code, func):
    m = re.search(r"\b" + re.escape(func) + r"\s*\([^;{]*\)\s*\{", code)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(code) and depth:
        depth += {"{": 1, "}": -1}.get(code[i], 0)
        i += 1
    return code[m.end():i - 1]


def check_constraints(code, spec):
    cons = spec.get("constraints") or {}
    if not cons:
        return []
    clean = _strip_comments_strings(code)
    func = spec.get("function") or "main"
    body = _function_body(clean, func) or ""
    problems = []
    if cons.get("require_recursion") and not re.search(r"\b" + re.escape(func) + r"\s*\(", body):
        problems.append(f"`{func}` must be recursive (call itself)")
    if cons.get("forbid_loops") and re.search(r"\b(for|while|do)\b", body):
        problems.append("loops are not allowed")
    for name in cons.get("forbid_builtins", []):
        if re.search(r"\b" + re.escape(name) + r"\s*\(", clean):
            problems.append(f"`{name}` is not allowed")
    for name in cons.get("require_calls", []):
        if not re.search(r"\b" + re.escape(name) + r"\s*\(", clean):
            problems.append(f"must use `{name}`")
    return problems


# ------------------------------------------------------------------ grade

def grade(code, spec, tests, visible=3):
    total = len(tests)
    report = {"frac": 0.0, "passed": 0, "total": total, "categories": {}, "load_error": None,
              "constraint_errors": [], "tests": [], "compiler_output": ""}
    is_program = spec.get("kind") == "program"
    try:
        if is_program:
            run = run_program_tests(code, [t["stdin"] for t in tests])
        else:
            run = run_function_tests(code, spec, tests)
    except CompilerMissing as e:
        report["load_error"] = {"type": "CompilerMissing", "msg": str(e), "line": None}
        report["categories"]["compile_error"] = 1
        return report

    report["compiler_output"] = run["compiler_output"]
    diags = diagnostics(run["compiler_output"])
    if not run["compile_ok"]:
        errs = [d for d in diags if d[0] == "error"] or [("error", None, run["compiler_output"][:300])]
        first = errs[0]
        cat = "compile_error"
        for pattern, c in ERROR_CATEGORIES:
            if re.search(pattern, first[2]):
                cat = c
                break
        if cat == "missing_function" and is_program:
            cat = "compile_error"
        report["load_error"] = {"type": "Compile error", "msg": first[2], "line": first[1]}
        report["categories"][cat] = 1
        return report

    warning_cats = []
    for _, line, msg in (d for d in diags if d[0] == "warning"):
        for pattern, wcat in WARNING_CATEGORIES:
            if re.search(pattern, msg) and wcat not in warning_cats:
                warning_cats.append(wcat)
    # Results that change between the two canary runs are garbage values. If the
    # compiler already explained where garbage comes from, blame that instead.
    garbage_cause = next((c for c in ("uninitialized_variable", "missing_return") if c in warning_cats),
                         "out_of_bounds")

    shown = 0
    for idx, (t, r) in enumerate(zip(tests, run["results"])):
        row = {"n": idx + 1, "ok": False, "edge": t.get("edge", False)}
        r = r or {"crash": "other_exception", "msg": "no result"}
        got_text = None
        if r.get("timeout"):
            cat, got_text = "timeout", r.get("msg") or f"no result after {PER_TEST_TIMEOUT:.0f}s (infinite loop?)"
        elif r.get("crash"):
            cat, got_text = r["crash"], r["msg"]
        elif is_program:
            if normalize_output(r["stdout"]) == normalize_output(t["expected"]):
                cat = None
            else:
                cat = classify_program_mismatch(normalize_output(t["expected"]),
                                                normalize_output(r["stdout"]), t.get("edge"))
        else:
            r0, r1 = r.get("r0", {}), r.get("r1", {})
            if not r0.get("__canary_ok", 1):
                cat = "out_of_bounds"  # wrote past the end of an array
            elif r0 != r1:
                cat = garbage_cause
            elif same_function(t["expected"], r0):
                cat = None
            elif ("return" in t["expected"] and r.get("stdout")
                  and _show_val(t["expected"]["return"], spec.get("returns", "int")) in r["stdout"]):
                cat = "printed_instead_of_return"
            else:
                cat = classify_function_mismatch(spec, t["expected"], r0, t.get("edge"))
            if r0 and got_text is None:
                got_text = show_result(spec, r0)

        if cat is None:
            row["ok"] = True
            report["passed"] += 1
        else:
            row["category"] = cat
            report["categories"][cat] = report["categories"].get(cat, 0) + 1
            if shown < visible:
                shown += 1
                if is_program:
                    row["stdin"] = t["stdin"]
                    row["expected"] = t["expected"]
                    row["got"] = r.get("stdout", "") + (f"\n[{got_text}]" if got_text else "")
                else:
                    row["call"] = call_str(spec, t["args"])
                    row["expected"] = show_result(spec, t["expected"])
                    row["got"] = got_text or ""
                    if cat == "out_of_bounds":
                        row["got"] += "  [read or wrote outside an array, or used an uninitialized value]"
                    elif cat in ("uninitialized_variable", "missing_return") and r.get("r0") != r.get("r1"):
                        row["got"] += "  [garbage value: changes from run to run]"
                    if r.get("stdout"):
                        row["stdout"] = r["stdout"][:500]
            else:
                row["hidden"] = True
        report["tests"].append(row)

    report["frac"] = report["passed"] / total if total else 0.0
    if report["passed"] < total:
        for wcat in warning_cats:
            report["categories"].setdefault(wcat, 1)
    violations = check_constraints(code, spec)
    if violations:
        report["constraint_errors"] = violations
        report["categories"]["constraint_violation"] = len(violations)
        report["frac"] = 0.0
    return report
