"""Problem specs: a built-in library of parameterized templates, plus validation
and test building for custom specs written by the AI.

A spec is small on purpose -- the AI (or a template) only supplies the prompt,
a reference solution, and a type description of each parameter. Test cases,
expected outputs and the worked examples in the prompt are all produced
procedurally from a seed.
"""
import random
import re
import textwrap

from . import dsl, fileio
from .grader import call_str, expected_outputs, show

TOPICS = {
    "python": ["loops", "strings", "lists", "dicts", "recursion", "conditionals",
               "nested_lists", "searching_sorting", "file_io"],
    # APSC 160 (C)
    "c": ["io", "conditionals", "loops", "functions", "arrays", "pointers", "strings", "2d_arrays",
          "file_io"],
}
LANGUAGES = list(TOPICS)

_TEMPLATES = []


def template(topic, difficulty, language="python"):
    def deco(fn):
        _TEMPLATES.append({"id": fn.__name__, "topic": topic, "difficulty": difficulty,
                           "language": language, "fn": fn})
        return fn
    return deco


def _spec(**kw):
    kw["reference"] = textwrap.dedent(kw["reference"]).strip() + "\n"
    kw["prompt"] = textwrap.dedent(kw["prompt"]).strip()
    return kw


# ------------------------------------------------------------------- loops

@template("loops", 1)
def count_multiples(rng):
    k = rng.choice([2, 3, 4, 5, 7])
    return _spec(
        title=f"Count multiples of {k}", function="count_multiples",
        inputs={"nums": "list[int(-40..40)](0..15)"},
        prompt=f"""
            Write a function `count_multiples(nums)` that returns how many integers in
            the list `nums` are divisible by **{k}**. Zero counts as a multiple.
        """,
        reference=f"""
            def count_multiples(nums):
                return sum(1 for x in nums if x % {k} == 0)
        """)


@template("loops", 1)
def sum_between(rng):
    a = rng.randint(-10, 5)
    b = a + rng.randint(5, 20)
    return _spec(
        title="Sum strictly between", function="sum_between",
        inputs={"nums": "list[int(-30..30)](0..15)"},
        prompt=f"""
            Write a function `sum_between(nums)` that returns the sum of the values in
            `nums` that are **strictly** greater than {a} and **strictly** less than {b}.
            Return `0` if there are none.
        """,
        reference=f"""
            def sum_between(nums):
                return sum(x for x in nums if {a} < x < {b})
        """)


@template("loops", 2)
def collatz_steps(rng):
    return _spec(
        title="Collatz steps", function="collatz_steps",
        inputs={"n": "int(1..300)"},
        prompt="""
            Starting from a positive integer `n`, repeatedly apply: if `n` is even, halve
            it; otherwise replace it with `3*n + 1`. Write `collatz_steps(n)` that returns
            the number of steps needed to reach `1` (`collatz_steps(1)` is `0`).
        """,
        reference="""
            def collatz_steps(n):
                steps = 0
                while n != 1:
                    n = n // 2 if n % 2 == 0 else 3 * n + 1
                    steps += 1
                return steps
        """)


# ----------------------------------------------------------------- strings

@template("strings", 1)
def count_vowels(rng):
    return _spec(
        title="Count vowels", function="count_vowels",
        inputs={"s": "str(0..20, text)"},
        prompt="""
            Write `count_vowels(s)` that returns the number of vowels (`a e i o u`,
            upper or lower case) in the string `s`.
        """,
        reference="""
            def count_vowels(s):
                return sum(1 for c in s.lower() if c in "aeiou")
        """)


@template("strings", 1)
def reverse_words(rng):
    return _spec(
        title="Reverse word order", function="reverse_words",
        inputs={"sentence": "sentence(0..6)"},
        prompt="""
            Write `reverse_words(sentence)` that returns a string with the words of
            `sentence` in reverse order, separated by single spaces. Words are separated
            by single spaces in the input. An empty string returns an empty string.
        """,
        reference="""
            def reverse_words(sentence):
                return " ".join(reversed(sentence.split()))
        """)


@template("strings", 2)
def caesar_shift(rng):
    n = rng.randint(1, 25)
    return _spec(
        title=f"Caesar shift by {n}", function="caesar_shift",
        inputs={"s": "str(0..20, text)"},
        prompt=f"""
            Write `caesar_shift(s)` that shifts every **lowercase** letter in `s` forward
            by {n} positions in the alphabet, wrapping around from `z` to `a`. All other
            characters (uppercase letters, spaces) stay the same.
        """,
        reference=f"""
            def caesar_shift(s):
                out = ""
                for c in s:
                    if "a" <= c <= "z":
                        out += chr((ord(c) - ord("a") + {n}) % 26 + ord("a"))
                    else:
                        out += c
                return out
        """)


@template("strings", 2)
def compress(rng):
    return _spec(
        title="Run-length encoding", function="compress",
        inputs={"s": "str(0..15, abc)"},
        prompt="""
            Write `compress(s)` that run-length encodes `s`: each maximal run of the same
            character becomes the character followed by the run length.
            For example `"aaabcc"` becomes `"a3b1c2"`.
        """,
        reference="""
            def compress(s):
                out = ""
                i = 0
                while i < len(s):
                    j = i
                    while j < len(s) and s[j] == s[i]:
                        j += 1
                    out += s[i] + str(j - i)
                    i = j
                return out
        """)


# ------------------------------------------------------------------- lists

@template("lists", 1)
def running_total(rng):
    return _spec(
        title="Running total", function="running_total",
        inputs={"nums": "list[int(-20..20)](0..12)"},
        prompt="""
            Write `running_total(nums)` that returns a **new** list where element `i` is
            the sum of `nums[0]` through `nums[i]`.
        """,
        reference="""
            def running_total(nums):
                out, acc = [], 0
                for x in nums:
                    acc += x
                    out.append(acc)
                return out
        """)


@template("lists", 2)
def remove_adjacent_duplicates(rng):
    return _spec(
        title="Remove adjacent duplicates", function="dedupe_runs",
        inputs={"nums": "list[int(0..3)](0..14)"},
        prompt="""
            Write `dedupe_runs(nums)` that returns a new list where consecutive repeated
            values are collapsed to one. For example `[1, 1, 2, 2, 2, 1]` becomes
            `[1, 2, 1]`.
        """,
        reference="""
            def dedupe_runs(nums):
                out = []
                for x in nums:
                    if not out or out[-1] != x:
                        out.append(x)
                return out
        """)


@template("lists", 2)
def largest_gap(rng):
    return _spec(
        title="Largest gap", function="largest_gap",
        inputs={"nums": "list[int(-50..50)](2..12)"},
        prompt="""
            Write `largest_gap(nums)` that returns the largest absolute difference between
            two **adjacent** elements of `nums`. You may assume `nums` has at least two
            elements.
        """,
        reference="""
            def largest_gap(nums):
                return max(abs(nums[i + 1] - nums[i]) for i in range(len(nums) - 1))
        """)


@template("lists", 2)
def rotate_left(rng):
    return _spec(
        title="Rotate left", function="rotate_left",
        inputs={"nums": "list[int(0..9)](0..10)", "k": "int(0..25)"},
        prompt="""
            Write `rotate_left(nums, k)` that returns a **new** list with the elements of
            `nums` rotated `k` positions to the left. `k` may be larger than the length of
            the list. Do not modify `nums`.
        """,
        reference="""
            def rotate_left(nums, k):
                if not nums:
                    return []
                k %= len(nums)
                return nums[k:] + nums[:k]
        """)


# ------------------------------------------------------------------- dicts

@template("dicts", 1)
def char_freq(rng):
    return _spec(
        title="Character frequencies", function="char_freq",
        inputs={"s": "str(0..15, abcd)"},
        prompt="""
            Write `char_freq(s)` that returns a dictionary mapping each character in `s`
            to the number of times it appears.
        """,
        reference="""
            def char_freq(s):
                d = {}
                for c in s:
                    d[c] = d.get(c, 0) + 1
                return d
        """)


@template("dicts", 2)
def group_by_length(rng):
    return _spec(
        title="Group words by length", function="group_by_length",
        inputs={"words": "list[word](0..10)"},
        prompt="""
            Write `group_by_length(words)` that returns a dictionary mapping each word
            length (an `int`) to the list of words with that length, in the order they
            appear in `words` (duplicates included).
        """,
        reference="""
            def group_by_length(words):
                d = {}
                for w in words:
                    d.setdefault(len(w), []).append(w)
                return d
        """)


@template("dicts", 2)
def top_scorer(rng):
    return _spec(
        title="Top scorer", function="top_scorer",
        inputs={"scores": "dict[word,int(0..10)](1..8)"},
        prompt="""
            `scores` maps student names to scores. Write `top_scorer(scores)` that returns
            the name with the highest score. If several names tie, return the one that
            comes first alphabetically. `scores` is never empty.
        """,
        reference="""
            def top_scorer(scores):
                best = max(scores.values())
                return min(name for name in scores if scores[name] == best)
        """)


# --------------------------------------------------------------- recursion

@template("recursion", 1)
def digit_sum(rng):
    return _spec(
        title="Recursive digit sum", function="digit_sum",
        inputs={"n": "int(0..99999)"},
        constraints={"require_recursion": True, "forbid_loops": True},
        prompt="""
            Write a **recursive** function `digit_sum(n)` that returns the sum of the
            digits of the non-negative integer `n`. Loops are not allowed.
        """,
        reference="""
            def digit_sum(n):
                if n < 10:
                    return n
                return n % 10 + digit_sum(n // 10)
        """)


@template("recursion", 2)
def count_target(rng):
    return _spec(
        title="Recursive count", function="count_target",
        inputs={"nums": "list[int(0..5)](0..12)", "target": "int(0..5)"},
        constraints={"require_recursion": True, "forbid_loops": True, "forbid_builtins": ["count"]},
        prompt="""
            Write a **recursive** function `count_target(nums, target)` that returns how
            many times `target` appears in `nums`. Loops and `list.count` are not allowed.
        """,
        reference="""
            def count_target(nums, target):
                if not nums:
                    return 0
                return (nums[0] == target) + count_target(nums[1:], target)
        """)


@template("recursion", 3)
def flatten(rng):
    return _spec(
        title="Flatten nested list", function="flatten",
        inputs={"items": "nested[int(0..9)](0..5)"},
        constraints={"require_recursion": True},
        prompt="""
            `items` is a list whose elements are integers or (possibly nested) lists of
            integers. Write a **recursive** function `flatten(items)` that returns a flat
            list of all the integers, in left-to-right order.
        """,
        reference="""
            def flatten(items):
                out = []
                for x in items:
                    if isinstance(x, list):
                        out += flatten(x)
                    else:
                        out.append(x)
                return out
        """)


# ------------------------------------------------------------ conditionals

@template("conditionals", 1)
def letter_grade(rng):
    return _spec(
        title="UBC letter grade", function="letter_grade",
        inputs={"score": "int(0..100)"},
        num_tests=18,
        edge_cases=[[90], [89], [85], [80], [76], [72], [68], [64], [60], [55], [50], [49]],
        prompt="""
            Write `letter_grade(score)` that converts a percentage (0-100) to a UBC letter
            grade: 90+ `A+`, 85+ `A`, 80+ `A-`, 76+ `B+`, 72+ `B`, 68+ `B-`, 64+ `C+`,
            60+ `C`, 55+ `C-`, 50+ `D`, otherwise `F`.
        """,
        reference="""
            def letter_grade(score):
                for cutoff, g in [(90, "A+"), (85, "A"), (80, "A-"), (76, "B+"), (72, "B"),
                                  (68, "B-"), (64, "C+"), (60, "C"), (55, "C-"), (50, "D")]:
                    if score >= cutoff:
                        return g
                return "F"
        """)


@template("conditionals", 2)
def classify_triangle(rng):
    return _spec(
        title="Classify a triangle", function="classify_triangle",
        inputs={"a": "int(1..6)", "b": "int(1..6)", "c": "int(1..6)"},
        edge_cases=[[1, 2, 3], [2, 2, 4], [3, 3, 3], [5, 3, 3]],
        prompt="""
            Write `classify_triangle(a, b, c)` that returns `"invalid"` if the side lengths
            cannot form a triangle (some side is >= the sum of the other two), otherwise
            `"equilateral"`, `"isosceles"` or `"scalene"`.
        """,
        reference="""
            def classify_triangle(a, b, c):
                x, y, z = sorted([a, b, c])
                if x + y <= z:
                    return "invalid"
                if a == b == c:
                    return "equilateral"
                if a == b or b == c or a == c:
                    return "isosceles"
                return "scalene"
        """)


# ------------------------------------------------------------ nested lists

@template("nested_lists", 1)
def row_sums(rng):
    return _spec(
        title="Row sums", function="row_sums",
        inputs={"grid": "grid[int(-9..9)](1..4, 1..5)"},
        prompt="""
            `grid` is a rectangular list of lists of integers. Write `row_sums(grid)` that
            returns a list containing the sum of each row.
        """,
        reference="""
            def row_sums(grid):
                return [sum(row) for row in grid]
        """)


@template("nested_lists", 2)
def transpose(rng):
    return _spec(
        title="Transpose", function="transpose",
        inputs={"grid": "grid[int(0..9)](1..4, 1..4)"},
        prompt="""
            Write `transpose(grid)` that returns a **new** grid whose rows are the columns
            of the rectangular grid `grid`.
        """,
        reference="""
            def transpose(grid):
                return [[grid[r][c] for r in range(len(grid))] for c in range(len(grid[0]))]
        """)


@template("nested_lists", 3)
def count_peaks(rng):
    return _spec(
        title="Count peaks", function="count_peaks",
        inputs={"grid": "grid[int(0..5)](1..5, 1..5)"},
        prompt="""
            A cell in `grid` is a *peak* if it is strictly greater than every neighbour
            directly above, below, left and right of it (cells on the border just have
            fewer neighbours). Write `count_peaks(grid)` that returns the number of peaks.
        """,
        reference="""
            def count_peaks(grid):
                rows, cols = len(grid), len(grid[0])
                count = 0
                for r in range(rows):
                    for c in range(cols):
                        v = grid[r][c]
                        ok = True
                        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            rr, cc = r + dr, c + dc
                            if 0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] >= v:
                                ok = False
                        count += ok
                return count
        """)


# ------------------------------------------------------- searching/sorting

@template("searching_sorting", 2)
def binary_search(rng):
    return _spec(
        title="Binary search", function="binary_search",
        inputs={"nums": "sortedlist[int(0..20)](0..12)", "target": "int(0..20)"},
        constraints={"forbid_builtins": ["index"]},
        prompt="""
            `nums` is sorted in increasing order with no duplicates. Write
            `binary_search(nums, target)` that returns the index of `target` in `nums`,
            or `-1` if it is not present. Do not use `list.index`.
        """,
        reference="""
            def binary_search(nums, target):
                lo, hi = 0, len(nums) - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if nums[mid] == target:
                        return mid
                    if nums[mid] < target:
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return -1
        """)


@template("searching_sorting", 2)
def insertion_sort(rng):
    return _spec(
        title="Sort without sorted()", function="my_sort",
        inputs={"nums": "list[int(-20..20)](0..12)"},
        constraints={"forbid_builtins": ["sorted", "sort"]},
        prompt="""
            Write `my_sort(nums)` that returns a **new** list with the elements of `nums`
            in increasing order. You may not use `sorted` or `list.sort`.
        """,
        reference="""
            def my_sort(nums):
                out = []
                for x in nums:
                    i = 0
                    while i < len(out) and out[i] <= x:
                        i += 1
                    out.insert(i, x)
                return out
        """)


@template("searching_sorting", 3)
def merge_sorted(rng):
    return _spec(
        title="Merge sorted lists", function="merge_sorted",
        inputs={"a": "sortedlist[int(0..30)](0..8)", "b": "sortedlist[int(0..30)](0..8)"},
        constraints={"forbid_builtins": ["sorted", "sort"]},
        prompt="""
            `a` and `b` are each sorted in increasing order. Write `merge_sorted(a, b)`
            that returns one sorted list containing every element of both (keep
            duplicates). You may not use `sorted` or `list.sort`.
        """,
        reference="""
            def merge_sorted(a, b):
                i = j = 0
                out = []
                while i < len(a) and j < len(b):
                    if a[i] <= b[j]:
                        out.append(a[i]); i += 1
                    else:
                        out.append(b[j]); j += 1
                return out + a[i:] + b[j:]
        """)


# ------------------------------------------------------------------ public

def list_templates(language=None):
    return [{k: t[k] for k in ("id", "language", "topic", "difficulty")} for t in _TEMPLATES
            if not language or t["language"] == language]


def pick_templates(count, topics=None, difficulty=2, seed=None, topic_weights=None, language="python"):
    """Choose `count` distinct templates, preferring the requested difficulty and
    (if given) topics weighted by how often the student gets them wrong."""
    rng = random.Random(seed)
    lang = [t for t in _TEMPLATES if t["language"] == language]
    pool = [t for t in lang if not topics or t["topic"] in topics] or list(lang)
    chosen = []
    while pool and len(chosen) < count:
        weights = []
        for t in pool:
            w = 1.0 / (1 + abs(t["difficulty"] - difficulty))
            if topic_weights:
                w *= 1 + 3 * topic_weights.get(t["topic"], 0)
            weights.append(w)
        t = rng.choices(pool, weights)[0]
        pool.remove(t)
        chosen.append(t)
    return chosen, rng


def build_from_templates(count, topics=None, difficulty=2, seed=None, topic_weights=None, points=10,
                         language="python"):
    chosen, rng = pick_templates(count, topics, difficulty, seed, topic_weights, language)
    specs = []
    for t in chosen:
        spec = t["fn"](rng)
        spec.update(topic=t["topic"], difficulty=t["difficulty"], template=t["id"], points=points,
                    language=t["language"])
        specs.append(normalize(spec))
    return specs


def normalize(spec):
    """Fill defaults, validate the DSL and reference, and attach worked examples."""
    spec.setdefault("language", "python")
    if spec["language"] == "c":
        return _normalize_c(spec)
    if spec["language"] != "python":
        raise ValueError(f"unsupported language {spec['language']!r}; use one of {LANGUAGES}")
    required = ["title", "function", "prompt", "reference", "inputs"]
    missing = [k for k in required if not spec.get(k)]
    if missing:
        raise ValueError(f"spec is missing: {', '.join(missing)}")
    if not isinstance(spec["inputs"], dict):
        raise ValueError("inputs must be an object mapping parameter name -> type string")
    for name, src in spec["inputs"].items():
        try:
            dsl.parse(src)
        except dsl.DSLError as e:
            raise ValueError(f"input {name!r}: {e}") from e
    _defaults(spec)
    _check_files(spec)
    params = ", ".join(spec["inputs"])
    spec.setdefault("starter", f"def {spec['function']}({params}):\n    # TODO: your code here\n    pass\n")
    # Validation run doubles as example generation.
    tests = build_tests(spec, seed="examples")
    spec["examples"] = [dict(_example_files(t), call=call_str(spec["function"], t["args"]),
                             result=show(t["expected"])) for t in _example_picks(tests)]
    return spec


def _check_files(spec):
    """Validate the optional file I/O fields (see fileio.py)."""
    spec.setdefault("file_data", {})
    if not isinstance(spec["file_data"], dict):
        raise ValueError("file_data must be an object mapping name -> type string")
    for name, src in spec["file_data"].items():
        try:
            dsl.parse(src)
        except dsl.DSLError as e:
            raise ValueError(f"file_data {name!r}: {e}") from e
        if name in spec.get("inputs", {}):
            raise ValueError(f"file_data {name!r} clashes with an input of the same name")
    if not isinstance(spec.get("input_files") or {}, dict) or not all(
            isinstance(v, str) for v in (spec.get("input_files") or {}).values()):
        raise ValueError("input_files must map file name -> template string")
    if not isinstance(spec.get("output_files") or [], list):
        raise ValueError("output_files must be a list of file names")
    fileio.check_templates(spec)


def _example_files(t):
    if not (t.get("files") or t.get("expected_files") or t.get("no_files")):
        return {}
    return {"files": t.get("files") or {}, "out_files": t.get("expected_files") or {},
            "no_files": bool(t.get("no_files"))}


def _defaults(spec):
    spec.setdefault("topic", "general")
    spec.setdefault("difficulty", 2)
    spec.setdefault("points", 10)
    spec.setdefault("num_tests", 12)
    spec.setdefault("visible_failures", 3)
    spec.setdefault("constraints", {})
    spec.setdefault("edge_cases", [])


C_HEADER = "#define _CRT_SECURE_NO_WARNINGS\n#include <stdio.h>\n#include <math.h>\n\n"
_C_TYPES = re.compile(r"^(const )?(int|double|char)(\[\](\[\d+\])?|\*)?$")


def _normalize_c(spec):
    from . import c_grader
    spec.setdefault("kind", "function")
    _defaults(spec)
    if spec["kind"] == "program":
        missing = [k for k in ("title", "prompt", "reference") if not spec.get(k)]
        if not spec.get("inputs") and not spec.get("file_data"):
            missing.append("inputs (or file_data)")
        if not spec.get("stdin") and not fileio.has_files(spec):
            missing.append("stdin (or input_files)")
        if missing:
            raise ValueError(f"C program spec is missing: {', '.join(missing)}")
        spec.setdefault("inputs", {})
        spec.setdefault("stdin", "")
        spec.setdefault("function", "main")
    elif spec["kind"] == "function":
        missing = [k for k in ("title", "function", "prompt", "reference", "params") if not spec.get(k)]
        if missing:
            raise ValueError(f"C function spec is missing: {', '.join(missing)}")
        spec.setdefault("returns", "void")
        if spec["returns"] not in ("void", "int", "double", "char"):
            raise ValueError("returns must be void, int, double or char")
        names = {p.get("name") for p in spec["params"]}
        for p in spec["params"]:
            if not p.get("name") or not _C_TYPES.match(p.get("type", "")):
                raise ValueError(f"bad param {p!r}: type must be like int, double, char, int*, "
                                 "const int[], double[], char[], const int[][5]")
            for ref in ("size_of", "rows_of", "out_len"):
                if ref in p and p[ref] not in names:
                    raise ValueError(f"param {p['name']}: {ref} refers to unknown param {p[ref]!r}")
            if (p["type"].endswith("[]") and not p["type"].startswith(("char", "const char"))
                    and not p.get("input") and not p.get("out_len") and not p.get("length")):
                raise ValueError(f"array param {p['name']} needs an input, out_len or length")
            if (not p["type"].endswith(("]", "*")) and not p.get("input")
                    and "size_of" not in p and "rows_of" not in p):
                raise ValueError(f"scalar param {p['name']} needs an input, size_of or rows_of")
        spec["inputs"] = {p["name"]: p["input"] for p in spec["params"] if p.get("input")}
    else:
        raise ValueError("kind must be 'function' or 'program'")
    if not isinstance(spec["inputs"], dict):
        raise ValueError("inputs must be an object mapping name -> type string")
    for name, src in spec["inputs"].items():
        try:
            dsl.parse(src)
        except dsl.DSLError as e:
            raise ValueError(f"input {name!r}: {e}") from e
    _check_files(spec)

    if spec["kind"] == "program":
        spec.setdefault("starter", C_HEADER + "int main(void)\n{\n    /* TODO: your code here */\n\n"
                                              "    return 0;\n}\n")
    else:
        default_ret = {"void": "", "int": "    return 0;\n", "double": "    return 0.0;\n",
                       "char": "    return ' ';\n"}
        spec.setdefault("starter", C_HEADER + c_grader.prototype(spec) + "\n{\n    /* TODO: your code here */\n\n"
                        + default_ret[spec["returns"]] + "}\n")
    tests = build_tests(spec, seed="examples")
    picks = _example_picks(tests)
    if spec["kind"] == "program":
        spec["examples"] = [dict(_example_files(t), stdin=t["stdin"], stdout=t["expected"])
                            for t in picks[:2]]
    else:
        spec["examples"] = [dict(_example_files(t), call=c_grader.call_str(spec, t["args"]),
                                 result=c_grader.show_result(spec, t["expected"])) for t in picks]
    return spec


def _example_picks(tests):
    random_ones = [t for t in tests if not t["edge"]]
    edges = [t for t in tests if t["edge"] and not t.get("no_files")]
    picks = random_ones[:2] + edges[:1]
    return picks or tests[:3]


def build_tests(spec, seed):
    """Generate inputs (+ file_data), render input files / stdin, then run the
    reference to get expected results and expected output files."""
    rng = random.Random(f"{seed}:{spec['function']}:{spec['title']}")
    names = list(spec["inputs"])
    data = spec.get("file_data") or {}
    fields = dict(spec["inputs"], **data)
    # explicit edge cases give the inputs; their file_data is generated
    edges = [list(e) + [dsl.generate(src, rng) for src in data.values()] for e in spec.get("edge_cases", [])]
    tests = dsl.make_tests(fields, rng, int(spec.get("num_tests", 12)), edges, spec.get("auto_edges", True))
    if spec.get("missing_file_test") and tests:
        tests.append(dict(tests[-1], edge=True, no_files=True))
    for t in tests:
        values = dict(zip(fields, t["args"]))
        t["args"] = t["args"][:len(names)]
        if data:
            t["data"] = {k: values[k] for k in data}
        if spec.get("input_files"):
            t["files"] = {} if t.get("no_files") else {
                name: fileio.render(tmpl, values) for name, tmpl in spec["input_files"].items()}
        if spec.get("kind") == "program":
            t["stdin"] = fileio.render(spec.get("stdin") or "", values)
    if spec.get("language") == "c":
        from . import c_grader
        return c_grader.expected_outputs(spec, tests)
    return expected_outputs(spec, tests)


from . import c_problems  # noqa: E402,F401  -- registers the C (APSC 160) templates
from . import file_problems  # noqa: E402,F401  -- registers the file I/O templates
