"""File I/O support shared by the Python and C graders.

A question can declare
    "input_files":  {"data.txt": "{len:values}\n{lines:values}\n"}   # templates
    "output_files": ["report.txt"]                                    # graded files
    "file_data":    {"values": "list[int(0..100)](1..12)"}            # generated values
                                                                      # usable in templates
    "missing_file_test": true    # one extra test runs with no input files at all

Templates use the same values as the question's inputs plus `file_data`:
    {x}        value; lists space-separated, grids one row per line
    {lines:x}  list, one item per line
    {csv:x}    list, comma-separated
    {len:x}    length of a list

Each test runs in its own empty folder containing only its input files, so the
program's relative `fopen("data.txt", "r")` works like on the student's machine.
"""
import os
import re

_FIELD = re.compile(r"\{([a-zA-Z_]+:)?([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _fmt(v, sep=" "):
    if isinstance(v, list):
        if v and isinstance(v[0], list):
            return "\n".join(" ".join(_fmt(x) for x in row) for row in v)
        return sep.join(_fmt(x) for x in v)
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def render(template, values):
    def sub(m):
        fn, key = (m.group(1) or "").rstrip(":"), m.group(2)
        if key not in values:
            return m.group(0)
        v = values[key]
        if fn == "len":
            return str(len(v))
        if fn == "lines":
            return _fmt(v, "\n")
        if fn == "csv":
            return _fmt(v, ",")
        return _fmt(v)
    return _FIELD.sub(sub, template)


def has_files(spec):
    return bool(spec.get("input_files") or spec.get("output_files") or spec.get("missing_file_test"))


def template_fields(spec):
    """Names a template may refer to."""
    return set(spec.get("inputs", {})) | set(spec.get("file_data", {}))


def check_templates(spec):
    known = template_fields(spec)
    templates = dict(spec.get("input_files") or {})
    if spec.get("stdin"):
        templates["stdin"] = spec["stdin"]
    for name, tmpl in templates.items():
        for m in _FIELD.finditer(tmpl):
            if m.group(2) not in known:
                raise ValueError(f"template for {name!r} uses unknown field {{{m.group(0)[1:-1]}}}; "
                                 f"known: {sorted(known)}")
    for name in list(spec.get("input_files") or {}) + list(spec.get("output_files") or []):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) or name.startswith("."):
            raise ValueError(f"bad file name {name!r} (letters, digits, _ . - only)")


def prepare_dir(path, files):
    os.makedirs(path, exist_ok=True)
    for name, content in (files or {}).items():
        with open(os.path.join(path, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)


def read_outputs(path, names):
    out = {}
    try:
        present = set(os.listdir(path))  # exact-case names, like a Linux grader sees them
    except OSError:
        present = set()
    for name in names or []:
        p = os.path.join(path, name)
        if name not in present:
            out[name] = None
            continue
        try:
            with open(p, encoding="utf-8", errors="replace", newline="") as fh:
                out[name] = fh.read(20000).replace("\r\n", "\n")
        except OSError:
            out[name] = None
    return out


def read_log(path):
    """Parse the C fopen/fclose interception log."""
    events = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if parts[0] == "OPEN" and len(parts) == 4:
                    events.append(("open", parts[1], parts[2], parts[3] == "1"))
                elif parts[0] == "CLOSE":
                    events.append(("close",))
                elif parts[0] == "NULL" and len(parts) == 2:
                    events.append(("null", parts[1]))
    except OSError:
        pass
    return events


def io_problems(events, spec):
    """Categories explained by how the program used fopen/fclose."""
    inputs = set(spec.get("input_files") or {})
    outputs = set(spec.get("output_files") or [])
    cats = set()
    opened_ok = closes = 0
    for e in events:
        if e[0] == "close":
            closes += 1
            continue
        if e[0] == "null":
            cats.add("unchecked_fopen")  # used the NULL that a failed fopen returned
            continue
        _, name, mode, ok = e
        base = os.path.basename(name.replace("\\", "/"))
        opened_ok += ok
        if base not in inputs | outputs:
            # includes a case mismatch ("Data.txt"): Windows would open it, but
            # PrairieLearn's Linux graders would not
            cats.add("wrong_filename")
        elif base in inputs and any(c in mode for c in "wa") and base not in outputs:
            cats.add("wrong_file_mode")  # would overwrite the data file
        elif base in outputs and "r" in mode and "+" not in mode and base not in inputs:
            cats.add("wrong_file_mode")
    if opened_ok > closes:
        cats.add("file_not_closed")
    return cats


def normalize(text):
    if text is None:
        return None
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)
