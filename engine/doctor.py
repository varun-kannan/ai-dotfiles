"""harness doctor: what loads at session start, against the caps, and whether the install has drifted."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import statistics
import subprocess
import time
from pathlib import Path

from . import BASE, SHARED, generate, project, tokens

SYNCED_DIRS = ("rules", "skills", "config", "engine", "bin")


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _descriptions(pattern):
    total = 0
    for path in glob.glob(os.path.expanduser(pattern)):
        m = re.search(r"^description:\s*(.+)$", _read(path), re.M)
        total += tokens(m.group(1)) if m else 0
    return total


def project_tokens(root):
    """Tokens of the project rule files a tool loads, following @imports one level."""
    seen, total = set(), 0
    queue = [root / "CLAUDE.md", root / "AGENTS.md"]
    for depth in range(2):
        nxt = []
        for path in queue:
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            text = _read(path)
            total += tokens(text)
            if depth == 0:
                nxt += [(path.parent / m).resolve() for m in re.findall(r"^@(\S+)$", text, re.M)]
        queue = nxt
    return total


def measured_first_turn(root, days=30):
    """Median context size of the first response in recent Claude Code sessions for this project."""
    folder = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root))
    cutoff, totals = time.time() - days * 86400, []
    for path in glob.glob(str(folder / "*.jsonl")):
        if os.path.getmtime(path) < cutoff:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 400:
                        break
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    m = o.get("message") or {}
                    u = m.get("usage")
                    if m.get("role") == "assistant" and u and not o.get("isSidechain"):
                        t = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                        if t:
                            totals.append(t)
                            break
        except OSError:
            pass
    return (int(statistics.median(totals)), len(totals)) if totals else (None, 0)


def tree_hash(base, dirs=SYNCED_DIRS):
    h = hashlib.sha1()
    for d in dirs:
        for path in sorted(Path(base, d).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                h.update(str(path.relative_to(base)).encode())
                h.update(path.read_bytes())
    return h.hexdigest()


def source_repo():
    src = _read(SHARED / "source").strip()
    return Path(src) if src and Path(src, "install.sh").is_file() else None


def source_head(src):
    """(commit, clean) of the source repo, or (None, False)."""
    try:
        head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "-C", str(src), "status", "--porcelain"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    return (head.stdout.strip() or None), head.returncode == 0 and not dirty.stdout.strip()


def run(cwd):
    """Return (lines, failed)."""
    caps = json.loads(_read(BASE / "config" / "harness-budgets.json") or "{}")
    session = caps.get("session", {})
    lines, failed = [], False

    def row(label, value, cap=None, note=""):
        nonlocal failed
        over = cap is not None and value > cap
        failed = failed or over
        lines.append("  %-4s %-34s %6d%s%s" % ("OVER" if over else "ok", label, value,
                                              " / %d" % cap if cap is not None else "", "  " + note if note else ""))

    lines.append("Loaded at every session start (estimated tokens)")
    global_rules = tokens(_read(Path.home() / ".claude" / "CLAUDE.md"))
    row("global rules (~/.claude/CLAUDE.md)", global_rules, session.get("global_rules"))
    desc = _descriptions("~/.claude/skills/*/SKILL.md") + _descriptions("~/.claude/agents/*.md") + _descriptions("~/.claude/commands/*.md")
    row("skill, agent, command descriptions", desc, session.get("descriptions"))

    root, why = project.locate(cwd)
    harness_total = global_rules + desc
    if root is None:
        lines.append("  --   no project here (%s)" % why)
    else:
        ptok = project_tokens(root)
        harness_total += ptok
        row("project files (%s)" % root.name, ptok, session.get("project_files"))
        text = _read(root / "AGENTS.md")
        if generate.BEGIN in text:
            block = text.split(generate.BEGIN, 1)[1].split(generate.END, 1)[0]
            row("  of which generated block", tokens(block), caps.get("project_block"))
        else:
            excluded = project.is_excluded(root, project.load_excludes(SHARED / "harness-exclude"))
            lines.append("  --   no generated block (%s)" % ("excluded" if excluded else "not set up yet"))
        median, n = measured_first_turn(root)
        if median:
            lines.append("")
            lines.append("Measured: median first-turn context over %d recent sessions here is %d tokens." % (n, median))
            lines.append("The harness accounts for about %d of that. The rest is Claude Code itself, tool and" % harness_total)
            lines.append("MCP schemas, plugins, and the first prompt. Disconnecting unused MCP servers and plugins")
            lines.append("is the larger saving.")

    lines.append("")
    lines.append("Install")
    src = source_repo()
    if src is None:
        lines.append("  --   source repo unknown (run install.sh once)")
    else:
        same = tree_hash(src) == tree_hash(SHARED)
        failed = failed or not same
        lines.append("  %-4s installed copy %s %s" % ("ok" if same else "DIFF", "matches" if same else "differs from", src))
        if not same:
            lines.append("       run ./install.sh in the repo, or commit: a clean new commit is installed at the next session start")
    settings = _read(Path.home() / ".claude" / "settings.json")
    for hook in ("session-start.py", "prompt-route.py", "pre-write-guard.sh", "post-write-audit.sh"):
        ok = hook in settings
        failed = failed or not ok
        lines.append("  %-4s Claude Code hook %s" % ("ok" if ok else "MISS", hook))
    fb = generate.find_fieldbook()
    lines.append("  %-4s fieldbook binary%s" % ("ok" if fb else "MISS", "" if fb else " (project memory is skipped without it)"))
    if (SHARED / "harness.off").exists():
        lines.append("  --   engine is switched off (~/.ai-rules/harness.off)")
    return lines, failed
