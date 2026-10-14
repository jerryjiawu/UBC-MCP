"""Tiny type language for procedurally generating test inputs.

A problem spec describes each parameter with a short string instead of listing
test cases, e.g.

    int(-40..40)                     integer in a range (inclusive)
    float(0..1)                      float rounded to 2 places
    bool
    str(0..12, lower)                string, length range + alphabet
                                     (lower|upper|alpha|alnum|digits|text, or literal chars like "abc")
    word                             a random English word
    sentence(1..6)                   words joined by single spaces
    choice(1|2|"x")                  one of the listed JSON literals
    list[int(0..9)](0..15)           list, element type + length range
    sortedlist[int(0..50)](0..10)    sorted list of *distinct* values
    dict[word,int(0..100)](1..8)     dict with distinct keys
    grid[int(-9..9)](1..4, 1..5)     rectangular 2D list (rows range, cols range)
    nested[int(0..9)](0..5)          arbitrarily nested lists (depth <= 3)

`generate(node, rng)` makes a random value; `generate(node, rng, mode="min")`
/ `"max"` make boundary values (shortest lists, range endpoints) which become
the automatic edge-case tests.
"""
import json
import random
import string

WORDS = (
    "apple tree cat dog river stone cloud maple ocean pixel lamp code byte "
    "ubc vancouver rain bridge salmon forest moss cedar coffee exam quiz loop "
    "list graph node orbit piano tiger zebra kiwi lemon mango berry sky sun"
).split()

ALPHABETS = {
    "lower": string.ascii_lowercase,
    "upper": string.ascii_uppercase,
    "alpha": string.ascii_letters,
    "alnum": string.ascii_letters + string.digits,
    "digits": string.digits,
    "text": string.ascii_letters + "    ",
}

KNOWN = {"int", "float", "bool", "str", "word", "sentence", "choice",
         "list", "sortedlist", "dict", "grid", "nested"}


class DSLError(ValueError):
    pass


def parse(src):
    node, pos = _parse_type(src.strip(), 0)
    if pos != len(src.strip()):
        raise DSLError(f"unexpected text at {pos} in {src!r}")
    return node


def _parse_type(s, i):
    j = i
    while j < len(s) and (s[j].isalnum() or s[j] == "_"):
        j += 1
    name = s[i:j]
    if name not in KNOWN:
        raise DSLError(f"unknown type {name!r} in {s!r}")
    params, args = [], []
    i = j
    if i < len(s) and s[i] == "[":
        i += 1
        while True:
            sub, i = _parse_type(s, _skip_ws(s, i))
            params.append(sub)
            i = _skip_ws(s, i)
            if s[i] == ",":
                i += 1
                continue
            if s[i] == "]":
                i += 1
                break
            raise DSLError(f"expected ',' or ']' in {s!r}")
    if i < len(s) and s[i] == "(":
        depth, j = 1, i + 1
        while j < len(s) and depth:
            depth += {"(": 1, ")": -1}.get(s[j], 0)
            j += 1
        if depth:
            raise DSLError(f"unclosed '(' in {s!r}")
        inner = s[i + 1:j - 1]
        args = [a.strip() for a in (inner.split("|") if name == "choice" else inner.split(","))]
        args = [a for a in args if a]
        i = j
    return {"name": name, "params": params, "args": args}, i


def _skip_ws(s, i):
    while i < len(s) and s[i] == " ":
        i += 1
    return i


def _range(arg, default, cast=int):
    if arg is None:
        return default
    lo, _, hi = arg.partition("..")
    return cast(lo), cast(hi or lo)


def _arg(node, k):
    return node["args"][k] if len(node["args"]) > k else None


def _pick_len(node, rng, mode, default=(0, 8), argi=0):
    lo, hi = _range(_arg(node, argi), default)
    if mode == "min":
        return lo
    if mode == "max":
        return hi
    return rng.randint(lo, hi)


def generate(node, rng, mode=None):
    if isinstance(node, str):
        node = parse(node)
    name = node["name"]
    elem = node["params"][0] if node["params"] else {"name": "int", "params": [], "args": []}

    if name == "int":
        lo, hi = _range(_arg(node, 0), (0, 10))
        return lo if mode == "min" else hi if mode == "max" else rng.randint(lo, hi)
    if name == "float":
        lo, hi = _range(_arg(node, 0), (0.0, 10.0), float)
        return lo if mode == "min" else hi if mode == "max" else round(rng.uniform(lo, hi), 2)
    if name == "bool":
        return rng.random() < 0.5
    if name == "str":
        n = _pick_len(node, rng, mode, (0, 10))
        alpha_arg = _arg(node, 1) or "lower"
        alphabet = ALPHABETS.get(alpha_arg, alpha_arg)
        return "".join(rng.choice(alphabet) for _ in range(n))
    if name == "word":
        return rng.choice(WORDS)
    if name == "sentence":
        n = _pick_len(node, rng, mode, (1, 6))
        return " ".join(rng.choice(WORDS) for _ in range(n))
    if name == "choice":
        opts = [_literal(a) for a in node["args"]]
        return opts[0] if mode == "min" else opts[-1] if mode == "max" else rng.choice(opts)
    if name == "list":
        n = _pick_len(node, rng, mode)
        return [generate(elem, rng, None) for _ in range(n)]
    if name == "sortedlist":
        n = _pick_len(node, rng, mode)
        return sorted(_distinct(elem, rng, n))
    if name == "dict":
        n = _pick_len(node, rng, mode, (0, 6))
        val = node["params"][1] if len(node["params"]) > 1 else {"name": "int", "params": [], "args": []}
        return {k: generate(val, rng, None) for k in _distinct(elem, rng, n)}
    if name == "grid":
        rows = _pick_len(node, rng, mode, (1, 4), 0)
        cols = _pick_len(node, rng, mode, (1, 4), 1)
        return [[generate(elem, rng, None) for _ in range(cols)] for _ in range(rows)]
    if name == "nested":
        n = _pick_len(node, rng, mode, (0, 5))
        return [_nested(elem, rng, 1) for _ in range(n)]
    raise DSLError(f"unknown type {name}")


def _nested(elem, rng, depth):
    if depth < 3 and rng.random() < 0.35:
        return [_nested(elem, rng, depth + 1) for _ in range(rng.randint(0, 3))]
    return generate(elem, rng, None)


def _distinct(elem, rng, n):
    seen = []
    for _ in range(n * 20):
        if len(seen) >= n:
            break
        v = generate(elem, rng, None)
        if v not in seen:
            seen.append(v)
    return seen


def _literal(a):
    try:
        return json.loads(a)
    except ValueError:
        return a


def make_tests(inputs, rng, num_tests, explicit_edges=(), auto_edges=True):
    """inputs: ordered {param: dsl}. Returns [{"args": [...], "edge": bool}]."""
    nodes = [parse(v) for v in inputs.values()]
    tests, seen = [], set()

    def add(args, edge):
        key = repr(args)
        if key not in seen:
            seen.add(key)
            tests.append({"args": args, "edge": edge})

    for args in explicit_edges:
        add(list(args), True)
    if auto_edges:
        for mode in ("min", "max"):
            add([generate(n, rng, mode) for n in nodes], True)
    for _ in range(num_tests * 10):
        if len(tests) >= num_tests:
            break
        add([generate(n, rng) for n in nodes], False)
    return tests
