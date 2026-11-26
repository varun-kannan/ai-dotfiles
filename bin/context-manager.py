#!/usr/bin/env python3
"""context-manager - choose which harness files fit one task and project.

Each agent, skill, domain rule and fieldbook memory file is scored against the
task's words and the project's detected tags. plan() fills the tier budget
(config/harness-budgets.json) from the highest score down; items marked "always"
are kept regardless of budget. task_matches() returns only what the task's own
words point to, which is what the Claude Code prompt hook names.

Words are compared after light stemming, so "testing" matches the tag "test" and
"caches" matches "cache".

Works from the repo or from the installed copy in ~/.ai-rules.

Usage:
    context-manager.py plan --task TEXT [--project DIR] [--tier auto|fast|standard|frontier]
    context-manager.py detect [--project DIR]
    context-manager.py measure
    context-manager.py --self-test

Optional per-project overrides live in DIR/.harness/config.json: "tier",
"exclude" (names never to load) and "pin" (names always to load).

Exit: 0 ok, 1 self-test failed or config error, 2 usage error.
"""
import os
import sys

# Run isolated (python3 -I): no PYTHONPATH, no user site, and not the current folder on the
# module path, which may be a repository with a file named like a standard module. A start
# without -I (from a #! line or a hook command) restarts once with it.
if not sys.flags.isolated and __name__ == "__main__":
    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__)] + sys.argv[1:])
import argparse
import importlib.util
import json
import re
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config"
CATEGORIES = ("agents", "skills", "rules", "memory")

sys.path.insert(0, str(BASE))
from engine import safefs  # noqa: E402
from engine.project import detect_tags  # noqa: E402


class ConfigError(Exception):
    pass


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def configs():
    try:
        return load_json(CONFIG / "harness-budgets.json"), load_json(CONFIG / "harness-relevance.json")
    except (OSError, ValueError) as exc:
        raise ConfigError("config error: %s" % exc)


def detect(project):
    return detect_tags(project)


def file_tokens(path):
    try:
        return (os.path.getsize(path) + 3) // 4
    except OSError:
        return 0


def stem(word):
    """Reduce a word so its inflections compare equal: tests/testing/test, caches/cached/cache,
    queries/query. The result is a key for matching, not always a word (database -> databas)."""
    word = word.lower()
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ied"):
        word = word[:-3] + "y"
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 4 and word.endswith("es"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def task_words(task):
    return {stem(w) for w in re.findall(r"[a-z0-9][a-z0-9+#-]*", task.lower())}


def project_config(project):
    text = safefs.read_text(project, Path(project) / ".harness" / "config.json")
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):      # deep nesting overflows the parser's stack
        return {}
    return data if isinstance(data, dict) else {}


def candidates(project, relevance):
    meta = {}
    try:
        meta = load_json(CONFIG / "skill-metadata.json").get("skills", {})
    except (OSError, ValueError):
        pass
    out = []
    for name, entry in relevance.get("agents", {}).items():
        out.append(("agents", name, BASE / "agents" / "definitions" / (name + ".md"), entry))
    for name, entry in relevance.get("skills", {}).items():
        always = meta.get(name, {}).get("relevance") == "always"
        out.append(("skills", name, BASE / "skills" / name / "SKILL.md", dict(entry, always=always or entry.get("always"))))
    for name, entry in relevance.get("rules", {}).items():
        out.append(("rules", name, BASE / "rules" / "domains" / (name + ".md"), entry))
    for name, entry in relevance.get("memory", {}).items():
        out.append(("memory", name, Path(project) / ".fieldbook" / "bank" / name, entry))
    rows = []
    for cat, name, path, entry in out:
        if cat == "memory":
            if not safefs.is_regular(project, path):
                continue
        elif not path.is_file():
            continue
        rows.append((cat, name, path, entry, file_tokens(path)))
    return rows


def score(entry, words, relevance):
    tags = {stem(t) for t in entry.get("tags", [])}
    hits = len(tags & words)
    if hits == 0:
        return 0.0
    base = entry.get("weight", 0.5) * min(1.0, 0.5 + 0.25 * hits)
    return round(base + relevance.get("priority_bonus", {}).get(entry.get("priority", "low"), 0.0), 3)


def load_router():
    path = BASE / "skills" / "model-router" / "router.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("model_router", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan(task, project, tier_flag="auto"):
    budgets, relevance = configs()
    project = Path(project).resolve()
    cfg = project_config(project)
    if tier_flag != "auto":
        tier, source = tier_flag, "flag"
    elif cfg.get("tier") in budgets.get("tiers", {}):
        tier, source = cfg["tier"], "project"
    else:
        router = load_router()
        tier, source = (router.analyze_complexity(task)[0], "auto") if router else ("standard", "default")
    budget = budgets["tiers"][tier]
    project_tags = {stem(t) for t in detect(project)}
    words = task_words(task) | project_tags
    exclude = set(x for x in cfg.get("exclude", []) if isinstance(x, str))
    pin = set(x for x in cfg.get("pin", []) if isinstance(x, str))

    ranked, skipped, warnings = [], [], []
    known = set()
    for cat, name, path, entry, toks in candidates(project, relevance):
        known.add(name)
        if name in exclude:
            skipped.append({"name": name, "category": cat, "reason": "excluded by project config"})
        elif entry.get("always") or name in pin:
            ranked.append((float("inf"), cat, name, path, toks))
        else:
            s = score(entry, words, relevance)
            if s:
                ranked.append((s, cat, name, path, toks))
            else:
                skipped.append({"name": name, "category": cat, "reason": "no task or project match"})
    for name in sorted(pin - known):
        warnings.append("pinned %s does not exist; ignored" % name)

    ranked.sort(key=lambda r: (r[0] != float("inf"), -r[0] if r[0] != float("inf") else 0))
    used = {c: 0 for c in CATEGORIES}
    total = 0
    selected = {c: [] for c in CATEGORIES}
    for s, cat, name, path, toks in ranked:
        fits = used[cat] + toks <= budget[cat] and total + toks <= budget["total"]
        if s != float("inf") and not fits:
            skipped.append({"name": name, "category": cat, "reason": "over %s budget" % cat})
            continue
        if not fits:
            warnings.append("%s kept although it exceeds the %s budget" % (name, cat))
        used[cat] += toks
        total += toks
        selected[cat].append({"name": name, "tokens": toks, "score": None if s == float("inf") else s, "path": str(path)})

    return {"tier": tier, "tier_source": source, "model": budget.get("model"), "project_tags": sorted(detect(project)),
            "budget": budget, "used": dict(used, total=total), "selected": selected, "skipped": skipped,
            "warnings": warnings}


def task_matches(task, project, per_category=4, use_config=True):
    """Items the task's own words point to (not project tags, not always-on items), best first.

    use_config=False ignores the project's .harness/config.json: in a repository the engine
    did not set up, that file is the repository's, not the user's.
    """
    _, relevance = configs()
    project = Path(project).resolve()
    cfg = project_config(project) if use_config else {}
    exclude = set(x for x in cfg.get("exclude", []) if isinstance(x, str))
    words = task_words(task)
    found = {c: [] for c in CATEGORIES}
    for cat, name, path, entry, toks in candidates(project, relevance):
        if entry.get("always") or name in exclude:
            continue
        s = score(entry, words, relevance)
        if s:
            found[cat].append((s, name))
    return {c: [n for _, n in sorted(v, key=lambda x: -x[0])[:per_category]] for c, v in found.items()}


def measure():
    _, relevance = configs()
    rows = [(toks, cat, name, str(path)) for cat, name, path, _e, toks in candidates(Path.cwd(), relevance)]
    for toks, cat, name, path in sorted(rows, reverse=True):
        print("%6d  %-7s %-28s %s" % (toks, cat, name, path))
    return 0


def self_test():
    failures = []

    def check(label, cond):
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp).resolve()
        (proj / "package.json").write_text(json.dumps({"devDependencies": {"react": "x"}}), encoding="utf-8")
        check("detect nodejs", "nodejs" in detect(proj))
        check("detect react", "react" in detect(proj))

        result = plan("fixing the failing tests in the react app", proj, tier_flag="standard")
        names = [i["name"] for c in result["selected"].values() for i in c]
        check("stemmed words match: testing-guide for 'tests'", "testing-guide" in names)
        check("budget not exceeded", result["used"]["total"] <= result["budget"]["total"])
        fast = plan("fix the failing tests", proj, tier_flag="fast")
        check("always-on security rule kept in the fast tier", "security" in [i["name"] for i in fast["selected"]["rules"]])

        (proj / ".fieldbook" / "bank").mkdir(parents=True)
        (proj / ".fieldbook" / "bank" / "06-gotchas.md").write_text("gotcha\n" * 20, encoding="utf-8")
        (proj / ".harness").mkdir()
        (proj / ".harness" / "config.json").write_text(json.dumps({"exclude": ["testing-guide"], "pin": ["nope"]}), encoding="utf-8")
        result = plan("fix a failing test", proj, tier_flag="standard")
        names = [i["name"] for c in result["selected"].values() for i in c]
        check("exclude honored", "testing-guide" not in names)
        check("gotchas memory selected for a fix task", "06-gotchas.md" in names)
        check("unknown pin reported", any("nope" in w for w in result["warnings"]))
        m = task_matches("why is the database migration failing", proj)
        check("task matches name database skill", "database-patterns" in m["skills"])
        check("task matches skip always-on items", "security" not in m["rules"])

        os.remove(proj / ".harness" / "config.json")
        os.mkfifo(proj / ".harness" / "config.json")
        check("FIFO config does not hang", project_config(proj) == {})

    for label in failures:
        print("FAIL", label)
    if not failures:
        print("ok")
    return 1 if failures else 0


def main(argv):
    parser = argparse.ArgumentParser(prog="context-manager.py")
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--task", required=True)
    p_plan.add_argument("--project", default=".")
    p_plan.add_argument("--tier", default="auto", choices=["auto", "fast", "standard", "frontier"])
    p_detect = sub.add_parser("detect")
    p_detect.add_argument("--project", default=".")
    sub.add_parser("measure")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.cmd == "plan":
            print(json.dumps(plan(args.task, args.project, args.tier), indent=2))
            return 0
        if args.cmd == "detect":
            print(json.dumps({"project_tags": detect(Path(args.project).resolve())}, indent=2))
            return 0
        if args.cmd == "measure":
            return measure()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
