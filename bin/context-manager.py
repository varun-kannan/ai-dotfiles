#!/usr/bin/env python3
"""context-manager - choose which harness files to load for one task and project.

Each agent, skill, and rule layer is scored against the task words and the
project's detected tags. Items are then added from the highest score down until
the tier budget (config/harness-budgets.json) is full. Items that match nothing
are skipped, so a generic task loads less.

Works from the repo root or from the installed copy in ~/.ai-rules.

Usage:
    context-manager.py plan --task TEXT [--project DIR] [--tier auto|fast|standard|frontier]
    context-manager.py detect [--project DIR]
    context-manager.py measure
    context-manager.py --self-test

Project overrides: DIR/.harness/project-config.json may set "tier", "exclude"
(list of names to never load) and "pin" (list of names to always load).

Exit: 0 ok, 1 self-test failed, 3 usage or config error.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config"
TOKENS_PER_CHAR = 0.25  # chars/4 estimate; a rough guide, not a tokenizer

LANG_FILES = {
    "package.json": ["nodejs"],
    "tsconfig.json": ["typescript"],
    "pyproject.toml": ["python"],
    "requirements.txt": ["python"],
    "setup.py": ["python"],
    "Cargo.toml": ["rust"],
    "pom.xml": ["java"],
    "build.gradle": ["java"],
    "build.gradle.kts": ["kotlin"],
    "Dockerfile": ["docker"],
    "docker-compose.yml": ["docker"],
    "compose.yaml": ["docker"],
}
DB_DIRS = ("migrations", "prisma", "alembic")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def detect(project):
    tags = set()
    for name, found in LANG_FILES.items():
        if (project / name).exists():
            tags.update(found)
    pkg_path = project / "package.json"
    if pkg_path.exists():
        try:
            pkg = load_json(pkg_path)
        except (OSError, ValueError):
            pkg = {}
        deps = dict(pkg.get("dependencies", {}))
        deps.update(pkg.get("devDependencies", {}))
        if "react" in deps:
            tags.add("react")
        if "typescript" in deps:
            tags.add("typescript")
    if "nodejs" in tags and "typescript" not in tags:
        tags.add("javascript")
    if (project / ".github" / "workflows").is_dir():
        tags.add("ci")
    if any((project / d).is_dir() for d in DB_DIRS):
        tags.add("database")
    return sorted(tags)


def tokens_for_chars(chars):
    return int(round(chars * TOKENS_PER_CHAR))


def file_tokens(path):
    try:
        return tokens_for_chars(os.path.getsize(path))
    except OSError:
        return 0


def task_words(task):
    return set(re.findall(r"[a-z0-9][a-z0-9+#-]*", task.lower()))


def score(entry, words, project_tags, always):
    tags = set(entry.get("tags", []))
    hits = len(tags & (words | project_tags))
    if hits == 0 and not (always or entry.get("always")):
        return 0.0
    weight = entry.get("weight", 0.5)
    base = weight * min(1.0, 0.5 + 0.25 * max(hits, 1))
    bonus = RELEVANCE["priority_bonus"].get(entry.get("priority", "low"), 0.0)
    return round(base + bonus, 3)


def candidates(project, words, project_tags):
    out = []
    skills_meta = load_json(CONFIG / "skill-metadata.json")["skills"]
    for name, entry in RELEVANCE["agents"].items():
        path = BASE / "agents" / "definitions" / (name + ".md")
        out.append(("agents", name, path, entry, file_tokens(path) if path.exists() else 0))
    for name, entry in RELEVANCE["skills"].items():
        path = BASE / "skills" / name / "SKILL.md"
        always = skills_meta.get(name, {}).get("relevance") == "always"
        out.append(("skills", name, path, dict(entry, always=always), file_tokens(path) if path.exists() else 0))
    for name, entry in RELEVANCE["rules"].items():
        path = BASE / "rules" / "domains" / (name + ".md")
        out.append(("rules", name, path, entry, file_tokens(path) if path.exists() else 0))
    harness = project / ".harness"
    for name, entry in RELEVANCE["memory"].items():
        path = harness / "memory" / name
        if path.exists():
            out.append(("memory", name, path, entry, file_tokens(path)))
    for path in sorted((harness / "rules").glob("*.md")) if (harness / "rules").is_dir() else []:
        out.append(("rules", "project:" + path.name, path, {"pinned": True}, file_tokens(path)))
    return out


def resolve_tier(task, tier_flag, project_cfg):
    if tier_flag != "auto":
        return tier_flag, "flag"
    if project_cfg.get("tier") in BUDGETS["tiers"]:
        return project_cfg["tier"], "project"
    router = load_router()
    if router is None:
        return "standard", "default"
    tier, _ = router.analyze_complexity(task)
    return tier, "auto"


def load_router():
    path = BASE / "skills" / "model-router" / "router.py"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("model_router", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan(task, project, tier_flag="auto"):
    project = Path(project).resolve()
    project_cfg_path = project / ".harness" / "project-config.json"
    try:
        project_cfg = load_json(project_cfg_path) if project_cfg_path.exists() else {}
    except (OSError, ValueError) as exc:
        raise SystemExit("bad project config %s: %s" % (project_cfg_path, exc))
    tier, source = resolve_tier(task, tier_flag, project_cfg)
    budget = BUDGETS["tiers"][tier]
    words = task_words(task)
    project_tags = set(detect(project))
    exclude = set(project_cfg.get("exclude", []))
    pin = set(project_cfg.get("pin", []))

    ranked = []
    for cat, name, path, entry, tokens in candidates(project, words, project_tags):
        key = name.split(":")[-1]
        if key in exclude or name in exclude:
            ranked.append((-1, cat, name, path, tokens, "excluded by project config"))
            continue
        if entry.get("pinned") or name in pin or key in pin:
            ranked.append((float("inf"), cat, name, path, tokens, None))
            continue
        s = score(entry, words, project_tags, False)
        if s == 0:
            ranked.append((0, cat, name, path, tokens, "no task or project match"))
        else:
            ranked.append((s, cat, name, path, tokens, None))

    ranked.sort(key=lambda r: -r[0] if r[0] != float("inf") else -1e9)
    used = {c: 0 for c in ("agents", "skills", "rules", "memory")}
    total = 0
    selected = {c: [] for c in used}
    skipped = []
    warnings = []
    for s, cat, name, path, tokens, reason in ranked:
        if reason is not None:
            skipped.append({"name": name, "category": cat, "reason": reason})
            continue
        if s == float("inf"):
            if used[cat] + tokens > budget[cat] or total + tokens > budget["total"]:
                warnings.append("pinned %s exceeds %s budget; loaded anyway" % (name, cat))
            used[cat] += tokens
            total += tokens
            selected[cat].append({"name": name, "tokens": tokens, "score": None, "path": str(path)})
            continue
        if used[cat] + tokens > budget[cat] or total + tokens > budget["total"]:
            skipped.append({"name": name, "category": cat, "reason": "over %s budget" % cat})
            continue
        used[cat] += tokens
        total += tokens
        selected[cat].append({"name": name, "tokens": tokens, "score": s, "path": str(path)})

    return {
        "tier": tier,
        "tier_source": source,
        "model": budget["model"],
        "project_tags": sorted(project_tags),
        "budget": budget,
        "used": dict(used, total=total),
        "selected": selected,
        "skipped": skipped,
        "warnings": warnings,
    }


def measure():
    rows = []
    for cat, name, path, _entry, tokens in candidates(Path.cwd(), set(), set()):
        rows.append((tokens, cat, name, str(path)))
    for tokens, cat, name, path in sorted(rows, reverse=True):
        print("%6d  %-7s %-28s %s" % (tokens, cat, name, path))
    return 0


def self_test():
    failures = []

    def check(label, cond):
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp)
        (proj / "package.json").write_text(json.dumps({"devDependencies": {"react": "x"}}), encoding="utf-8")
        check("detect nodejs", "nodejs" in detect(proj))
        check("detect react", "react" in detect(proj))
        check("detect javascript when no typescript", "javascript" in detect(proj))

        result = plan("fix a failing test in the react app", proj, tier_flag="standard")
        names = [i["name"] for c in result["selected"].values() for i in c]
        check("testing-guide selected for test task", "testing-guide" in names)
        check("budget not exceeded", result["used"]["total"] <= result["budget"]["total"])

        (proj / ".harness").mkdir()
        (proj / ".harness" / "project-config.json").write_text(
            json.dumps({"exclude": ["testing-guide"]}), encoding="utf-8")
        result = plan("fix a failing test", proj, tier_flag="standard")
        names = [i["name"] for c in result["selected"].values() for i in c]
        check("exclude honored", "testing-guide" not in names)

        result = plan("fix a failing test", proj, tier_flag="fast")
        check("fast tier total within budget", result["used"]["total"] <= result["budget"]["total"])

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
    parser.print_usage(sys.stderr)
    return 3


try:
    BUDGETS = load_json(CONFIG / "harness-budgets.json")
    RELEVANCE = load_json(CONFIG / "harness-relevance.json")
except (OSError, ValueError) as exc:
    sys.exit("config error: %s" % exc)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
