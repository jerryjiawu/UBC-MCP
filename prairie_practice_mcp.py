"""MCP server for PrairiePractice: lets an agent build PrairieLearn-style practice
exams, share them as files, and read the student's error history.

The agent never writes test cases or full problem files token by token:
  * `generate_practice_set` assembles problems from built-in parameterized
    templates (zero problem text written by the agent), optionally weighted
    toward topics the student keeps getting wrong.
  * `create_custom_problem` takes a compact spec (prompt + reference solution +
    a one-line type per parameter); tests, expected outputs and worked examples
    are generated procedurally from it.

Questions can be Python or C (APSC 160 style: function questions with a given
prototype, or whole programs using scanf/printf). C needs `pip install ziglang`.

The student answers in the local web app (`open_practice_app`).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from prairie_practice import grader, problems, store  # noqa: E402

PORT = int(os.getenv("PRAIRIE_PRACTICE_PORT", "5070"))
APP_URL = f"http://127.0.0.1:{PORT}"
APP_LOG = os.path.join(store.DATA_DIR, "app.log")

mcp = FastMCP("prairie-practice")


def _app_running():
    try:
        with urllib.request.urlopen(f"{APP_URL}/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _ensure_app():
    if _app_running():
        return True
    os.makedirs(store.DATA_DIR, exist_ok=True)
    venv_py = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    python = venv_py if os.path.exists(venv_py) else sys.executable
    if os.name == "nt":
        # MCP clients run this server inside a Windows job object that kills every
        # descendant when the session ends (and disallows breakaway). Processes
        # created through WMI aren't in that job, so the app outlives the session.
        cmd = f'cmd.exe /c ""{python}" -m prairie_practice.app >> "{APP_LOG}" 2>&1"'
        ps = ("$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly "
              "-Property @{ShowWindow=[uint16]0}; "
              "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
              "@{CommandLine=$env:PP_CMD; CurrentDirectory=$env:PP_DIR; ProcessStartupInformation=$si}")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=30,
                       env=dict(os.environ, PP_CMD=cmd, PP_DIR=PROJECT_ROOT),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        with open(APP_LOG, "a", encoding="utf-8") as log:
            subprocess.Popen([python, "-m", "prairie_practice.app"], cwd=PROJECT_ROOT,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(30):
        time.sleep(0.3)
        if _app_running():
            return True
    return False


def _set_summary(set_id, path):
    data = store.get_set(set_id)
    return {
        "set_id": set_id,
        "title": data["title"],
        "shareable_file": path,
        "app_url": APP_URL,
        "questions": [{"q": i + 1, "title": q["title"], "language": q.get("language", "python"),
                       "kind": q.get("kind", "function"), "topic": q["topic"],
                       "difficulty": q["difficulty"], "points": q["points"],
                       "example": q["examples"][0] if q.get("examples") else None}
                      for i, q in enumerate(data["questions"])],
        "settings": data["settings"],
    }


@mcp.tool()
def list_problem_templates(language: str | None = None) -> dict:
    """List the built-in procedural problem templates (id, language, topic,
    difficulty 1-3) and the valid topic names per language ("c" or "python")."""
    return {"topics": problems.TOPICS, "templates": problems.list_templates(language)}


@mcp.tool()
def generate_practice_set(title: str, count: int = 4, topics: list[str] | None = None,
                          difficulty: int = 2, target_weak_topics: bool = False,
                          time_limit_min: int = 50, max_attempts: int = 5,
                          points_per_question: int = 10, seed: int | None = None,
                          language: str = "c") -> dict:
    """Create a PrairieTest-style practice exam from procedural templates and save
    it as a shareable .ubcprac.json file.

    language: "c" (APSC 160: function questions with a given prototype, plus
        whole programs using scanf/printf) or "python".
    topics: subset of list_problem_templates()['topics'][language]; omit for all.
        C topics: io, conditionals, loops, functions, arrays, pointers, strings, 2d_arrays.
    difficulty: 1 (intro) .. 3 (hard); templates near this level are preferred.
    target_weak_topics: weight topic choice by the student's tracked error rate.
    time_limit_min: 0 = untimed. max_attempts: 0 = unlimited.
    Each question gets fresh randomized tests every time the exam is started."""
    if language not in problems.LANGUAGES:
        return {"error": f"language must be one of {problems.LANGUAGES}"}
    weights = store.topic_weakness() if target_weak_topics else None
    try:
        specs = problems.build_from_templates(max(1, min(count, 12)), topics, difficulty, seed,
                                              weights, points_per_question, language)
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    set_id, path = store.save_set(title, specs, time_limit_min, max_attempts)
    return _set_summary(set_id, path)


@mcp.tool()
def create_custom_problem(title: str, prompt: str, reference: str, language: str = "c",
                          kind: str = "function", function: str | None = None,
                          inputs: dict[str, str] | None = None, params: list[dict] | None = None,
                          returns: str = "void", stdin: str | None = None,
                          topic: str = "general", difficulty: int = 2,
                          points: int = 10, constraints: dict | None = None,
                          edge_cases: list[list] | None = None, num_tests: int = 12,
                          set_id: str | None = None, new_set_title: str | None = None,
                          time_limit_min: int = 50, max_attempts: int = 5) -> dict:
    """Add a custom coding question from a compact spec. Do NOT write test cases:
    they are generated procedurally from the input types and graded against `reference`.

    prompt: problem statement (supports `code`, **bold**, ```blocks```). Examples
        are appended automatically.
    reference: a correct solution in `language`.

    language="c", kind="function" (APSC 160 style):
        function: name, e.g. "min_max". returns: void|int|double|char.
        params: ordered list, each {"name", "type", ...} with type one of
          int, double, char, int*, double*, const int[], int[], const double[],
          double[], const char[] (string), char[] (string modified in place),
          const int[][N] / int[][N] (2D, N columns). Plus one of:
          "input": <type string, see below>   value comes from the generator
          "size_of": "<array param>"          int set to that array's length
          "rows_of": "<2D param>"             int set to that grid's row count
          "out_len": "<array param>"          output array, same length
          (pointer params without "input" are output-only.)
        The return value, every pointer and every non-const array are checked.
        e.g. [{"name": "data", "type": "const int[]", "input": "list[int(-9..9)](1..10)"},
              {"name": "size", "type": "int", "size_of": "data"},
              {"name": "max", "type": "int*"}]
    language="c", kind="program": a whole program read via scanf, printed via printf.
        inputs: {name: type}; stdin: template like "{len:nums}\n{nums}\n" ({x} =
        value, lists space-separated, grids one row per line, {len:x} = length).
        Output must match exactly (trailing whitespace ignored).
    language="python": function + inputs {param: type}.

    Input types: int(lo..hi), float(lo..hi), bool,
        str(lo..hi, lower|upper|alpha|alnum|digits|text|<literal chars>), word,
        sentence(lo..hi), choice(a|b|c), list[T](lenlo..lenhi),
        sortedlist[T](lo..hi) (distinct, sorted), dict[K,V](lo..hi),
        grid[T](rows lo..hi, cols lo..hi), nested[T](lo..hi).
        e.g. {"nums": "list[int(-50..50)](0..15)", "k": "int(1..5)"}.
        Length/value ranges are preconditions: boundary tests use their endpoints.
    constraints: optional {"require_recursion": bool, "forbid_loops": bool,
        "forbid_builtins": ["sorted", ...], "require_calls": ["strlen", ...] (C only)}
        -- checked statically; violations score 0.
    edge_cases: optional explicit argument lists, e.g. [[[]], [[0]]].
    set_id: add to an existing set; otherwise a new set named new_set_title (or title)."""
    spec = {"title": title, "prompt": prompt, "reference": reference, "language": language,
            "topic": topic, "difficulty": difficulty, "points": points,
            "constraints": constraints or {}, "edge_cases": edge_cases or [],
            "num_tests": max(4, min(num_tests, 40))}
    if function:
        spec["function"] = function
    if inputs:
        spec["inputs"] = inputs
    if language == "c":
        spec["kind"] = kind
        if kind == "function":
            spec.update(params=params or [], returns=returns)
        else:
            spec["stdin"] = stdin
    try:
        spec = problems.normalize(spec)
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    if set_id:
        store.add_question(set_id, spec)
        path = store.export_set(set_id)
    else:
        set_id, path = store.save_set(new_set_title or title, [spec], time_limit_min, max_attempts)
    return _set_summary(set_id, path)


@mcp.tool()
def list_practice_sets() -> list:
    """List saved practice sets with question counts, topics and whether an exam is in progress."""
    return store.list_sets()


@mcp.tool()
def export_practice_set(set_id: str, dest_dir: str | None = None) -> dict:
    """Write a practice set to a shareable .ubcprac.json file (default folder:
    prairie_practice/sets). Anyone can import it into their own copy of the app."""
    path = store.export_set(set_id, dest_dir or store.SETS_DIR)
    return {"path": path}


@mcp.tool()
def import_practice_set(path: str) -> dict:
    """Import a shared .ubcprac.json file. Its reference solutions run locally to
    generate tests, so only import files from trusted people."""
    with open(os.path.join(PROJECT_ROOT, path) if not os.path.isabs(path) else path,
              encoding="utf-8") as fh:
        data = json.load(fh)
    try:
        set_id, out = store.import_set_data(data)
    except ValueError as e:
        return {"error": str(e)}
    return _set_summary(set_id, out)


@mcp.tool()
def get_error_stats() -> dict:
    """The student's tracked mistakes: counts per error category, per-topic error
    rates, and the current (frequency-adjusted) penalty for each category. Use it
    to choose topics for the next practice set."""
    table, adaptive = store.penalty_table()
    s = store.stats()
    return {"attempts": s["attempts"], "perfect_attempts": s["perfect_attempts"],
            "by_category": s["by_category"], "by_topic": s["by_topic"],
            "penalties": table, "adaptive": adaptive,
            "weakest_topics": sorted(store.topic_weakness().items(), key=lambda kv: -kv[1])[:3]}


@mcp.tool()
def get_attempt_history(limit: int = 20) -> list:
    """Most recent graded attempts: set, question, score, points awarded,
    deduction applied and error categories."""
    return store.stats()["recent"][:max(1, min(limit, 40))]


@mcp.tool()
def set_error_penalty(category: str, points: float) -> dict:
    """Set the base point penalty for an error category (see get_error_stats for
    names). Applies to future attempts."""
    try:
        store.set_penalty(category, points)
    except ValueError as e:
        return {"error": str(e), "categories": list(grader.CATEGORIES)}
    table, _ = store.penalty_table()
    return next(r for r in table if r["category"] == category)


@mcp.tool()
def configure_adaptive_penalties(every: int | None = None, step: float | None = None,
                                 cap: float | None = None, max_per_attempt: float | None = None) -> dict:
    """Tune how frequent errors get more expensive: every `every` occurrences add
    `step` points to that category's penalty, up to `cap`. `max_per_attempt`
    limits the total deduction from one wrong attempt."""
    return store.set_adaptive(every=every, step=step, cap=cap, max_per_attempt=max_per_attempt)


@mcp.tool()
def open_practice_app(open_browser: bool = True, set_id: str | None = None) -> dict:
    """Start the local PrairieLearn-style exam app (if not already running) and
    optionally open it in the browser -- at a specific set's exam if set_id is given."""
    if not _ensure_app():
        return {"error": f"app failed to start; see {APP_LOG}"}
    url = APP_URL
    if set_id:
        open_inst = next((s["open_instance"] for s in store.list_sets() if s["id"] == set_id), None)
        url = f"{APP_URL}/instance/{open_inst}" if open_inst else APP_URL
    if open_browser:
        webbrowser.open(url)
    return {"url": url}


if __name__ == "__main__":
    mcp.run()
