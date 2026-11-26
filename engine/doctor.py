"""harness doctor: what loads at session start, against the caps, and whether the install is healthy."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shlex
import statistics
import subprocess
import time
from pathlib import Path

from . import BASE, SHARED, generate, harness_off, project, safefs, tokens

# What install.sh copies, as (path in the repo, path in an installed release).
SYNCED = (("bin", "bin"), ("engine", "engine"), ("rules", "rules"), ("config", "config"), ("skills", "skills"),
          ("shell", "shell"), ("agents/definitions", "agents/definitions"))
IGNORED = {".DS_Store", "__pycache__"}
HOOKS = ("session-start.py", "prompt-route.py", "pre-write-guard.sh", "post-write-audit.sh")
IMPORT_RE = re.compile(r"(?m)^@(\S+)\s*$")


def _read_home(path, limit=2_000_000):
    """Read a file the user owns (not project content), capped."""
    try:
        with open(path, "rb") as fh:
            return fh.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _descriptions(pattern):
    total = 0
    for path in glob.glob(os.path.expanduser(pattern)):
        m = re.search(r"^description:\s*(.+)$", _read_home(path, 50_000), re.M)
        total += tokens(m.group(1)) if m else 0
    return total


def project_tokens(root):
    """Tokens of the project rule files Claude Code loads, following @imports inside the project only."""
    root = Path(root)
    seen, total = set(), 0
    queue = [root / n for n in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")]
    if not any(safefs.exists(root, p) for p in queue):
        queue.append(root / "AGENTS.md")
    for depth in range(5):
        nxt = []
        for path in queue:
            if path in seen:
                continue
            seen.add(path)
            text = safefs.read_text(root, path)
            if text is None:
                continue
            total += tokens(text)
            for ref in IMPORT_RE.findall(text):
                target = Path(os.path.normpath(str(path.parent / ref)))
                try:
                    target.relative_to(root)
                except ValueError:
                    continue
                nxt.append(target)
        queue = nxt
    return total


def measured_first_turn(root, days=30):
    """Median context size of the first response in recent Claude Code sessions for this project."""
    folder = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root))
    cutoff, totals = time.time() - days * 86400, []
    for path in glob.glob(str(folder / "*.jsonl")):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i > 400:
                        break
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    m = o.get("message") if isinstance(o, dict) else None
                    u = m.get("usage") if isinstance(m, dict) else None
                    if isinstance(u, dict) and m.get("role") == "assistant" and not o.get("isSidechain"):
                        t = sum(u.get(k, 0) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                        if t:
                            totals.append(t)
                            break
        except OSError:
            pass
    return (int(statistics.median(totals)), len(totals)) if totals else (None, 0)


def _files(base, rel):
    top = Path(base, rel)
    out = {}
    for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED]
        for f in filenames:
            if f in IGNORED or f.endswith(".pyc"):
                continue
            full = Path(dirpath) / f
            out[str(full.relative_to(top))] = full
    return out


def tree_hash(base, installed=False):
    """Hash of exactly what install copies. installed=True reads a release folder's layout."""
    h = hashlib.sha1()
    for src_rel, dst_rel in SYNCED:
        rel = dst_rel if installed else src_rel
        for name, full in sorted(_files(base, rel).items()):
            h.update(("%s/%s" % (dst_rel, name)).encode())
            try:
                h.update(full.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest()


def source_repo():
    src = _read_home(SHARED / "source").strip()
    return Path(src) if src and Path(src, "install.sh").is_file() else None


def _git(src, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["LC_ALL"] = "C"
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(src)] + list(args), capture_output=True,
                              text=True, timeout=5, env=env, cwd="/", stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _template_dir_set(folder):
    """True when git's global init.templateDir resolves to folder."""
    r = _git(Path.home(), "config", "--global", "--path", "--get", "init.templateDir")
    if r is None or r.returncode != 0 or not r.stdout.strip():
        return False
    return os.path.realpath(r.stdout.strip()) == os.path.realpath(str(folder))


def source_head(src):
    """(commit, clean) of the source repo, or (None, False)."""
    head = _git(src, "rev-parse", "HEAD")
    status = _git(src, "status", "--porcelain")
    if head is None or status is None or head.returncode != 0 or status.returncode != 0:
        return None, False
    return head.stdout.strip() or None, not status.stdout.strip()


LOCAL_COMMIT = ("commit: ", "commit (amend): ", "commit (initial): ")


def committed_here(src, installed, head):
    """True when every step from the installed commit to HEAD was a commit made in this checkout.

    Read from the reflog. Commits that arrived by pull, merge, fetch, checkout, reset or
    rebase came from somewhere else and are not installed without a deliberate ./install.sh.
    """
    try:
        with open(Path(src) / ".git" / "logs" / "HEAD", encoding="utf-8", errors="replace") as fh:
            entries = fh.read().splitlines()[-2000:]
    except OSError:
        return False
    steps = []
    for line in entries:
        meta, _, message = line.partition("\t")
        parts = meta.split(" ")
        if len(parts) >= 2:
            steps.append((parts[1], message))
    starts = [i for i, (new, _) in enumerate(steps) if new == installed]
    if not starts:
        return False
    later = steps[starts[-1] + 1:]
    return bool(later) and later[-1][0] == head and all(m.startswith(LOCAL_COMMIT) for _, m in later)


def update_allowed(src):
    """True when the source repo's HEAD may be installed without asking.

    Only a clean tree, on the branch that was installed, at a commit that descends
    from the installed one through commits made in this checkout. Another branch, an
    older commit, a rewritten history, pulled or merged commits, or an install made
    from a dirty tree never installs anything automatically.
    """
    head, clean = source_head(src)
    installed = _read_home(SHARED / "installed-commit").strip()
    branch = _read_home(SHARED / "installed-branch").strip()
    if not head or not clean or head == installed or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", installed):
        return False
    cur = _git(src, "symbolic-ref", "--short", "HEAD")
    anc = _git(src, "merge-base", "--is-ancestor", installed, head)
    return cur is not None and anc is not None and cur.stdout.strip() == branch and anc.returncode == 0 \
        and committed_here(src, installed, head)


def _words(command):
    try:
        return [os.path.expanduser(os.path.expandvars(w)) for w in shlex.split(command)]
    except ValueError:
        return []


def _hooks_registered():
    """{hook name: problem or ""} from ~/.claude/settings.json and the hook files themselves."""
    out = {}
    try:
        cfg = json.loads(_read_home(Path.home() / ".claude" / "settings.json") or "{}")
    except ValueError:
        return {h: "settings.json is not valid JSON" for h in HOOKS}
    commands = []
    for groups in (cfg.get("hooks") or {}).values() if isinstance(cfg, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for hook in (group.get("hooks") or []) if isinstance(group, dict) else []:
                if isinstance(hook, dict) and isinstance(hook.get("command"), str):
                    commands.append(hook["command"])
    for name in HOOKS:
        path = str(Path.home() / ".claude" / "hooks" / name)
        if not any(path in _words(c) for c in commands):
            out[name] = "not registered in settings.json"
        elif not os.access(path, os.X_OK):
            out[name] = "registered but the file is missing or not executable"
        else:
            out[name] = ""
    return out


def run(cwd):
    """Return (lines, failed)."""
    try:
        caps = json.loads(_read_home(BASE / "config" / "harness-budgets.json") or "{}")
    except ValueError:
        caps = {}
    session = caps.get("session", {})
    lines, failed = [], False

    def row(label, value, cap=None, note=""):
        nonlocal failed
        over = cap is not None and value > cap
        failed = failed or over
        lines.append("  %-4s %-36s %6d%s%s" % ("OVER" if over else "ok", label, value,
                                              " / %d" % cap if cap is not None else "", "  " + note if note else ""))

    lines.append("Loaded at every session start (estimated tokens)")
    global_rules = tokens(_read_home(Path.home() / ".claude" / "CLAUDE.md"))
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
        state = generate._load(generate._state_path(root), {})
        mode = state.get("mode", "full")
        target = generate._paths(root, mode)[0]
        text = safefs.read_text(root, target) or ""
        if generate.block_state(text, generate.BEGIN, generate.END) == "ok":
            block = text.split(generate.BEGIN, 1)[1].split(generate.END, 1)[0]
            row("  of which generated block (%s mode)" % mode, tokens(block), caps.get("project_block"))
        else:
            excluded = project.is_excluded(root, project.load_excludes(SHARED / "harness-exclude"), skip_file=False) \
                or generate.skip_file_holds(root)
            reason = ("excluded" if excluded else "you removed it; `harness init` brings it back" if state.get("removed")
                      else state.get("blocked") or "not set up yet")
            lines.append("  --   no generated block (%s)" % reason)
        median, n = measured_first_turn(root)
        if median:
            lines.append("")
            lines.append("Measured: median first-turn context over %d recent sessions here is %d tokens." % (n, median))
            lines.append("The harness accounts for about %d of that. The rest is Claude Code itself, tool and" % harness_total)
            lines.append("MCP schemas, plugins, and the first prompt.")

    lines.append("")
    lines.append("Install")
    src = source_repo()
    current = SHARED / "current"
    if src is None:
        lines.append("  --   source repo unknown (run install.sh once)")
    elif not current.exists():
        failed = True
        lines.append("  MISS installed release (~/.ai-rules/current); run ./install.sh")
    else:
        same = tree_hash(src) == tree_hash(current.resolve(), installed=True)
        failed = failed or not same
        lines.append("  %-4s installed copy %s %s" % ("ok" if same else "DIFF", "matches" if same else "differs from", src))
        installed = _read_home(SHARED / "installed-commit").strip()
        if installed == "uncommitted":
            lines.append("       installed from uncommitted changes, so automatic updates are off until a clean ./install.sh")
        elif not same:
            lines.append("       run ./install.sh. A commit you make here on the installed branch is installed at the next")
            lines.append("       session start; commits that arrive by pull or merge are not, until you run ./install.sh")
    claude = (Path.home() / ".claude").is_dir()
    if not claude:
        lines.append("  --   Claude Code is not installed (~/.claude missing); its hooks were not set up")
    for name, problem in (_hooks_registered().items() if claude else ()):
        failed = failed or bool(problem)
        lines.append("  %-4s Claude Code hook %s%s" % ("ok" if not problem else "MISS", name, " (%s)" % problem if problem else ""))
    # The git and shell layers are reported, not failed on: you may have chosen to leave them out.
    template = Path.home() / ".git-templates" / "hooks"
    missing = [h for h in ("pre-commit", "commit-msg", "pre-applypatch", "applypatch-msg", "post-checkout", "post-merge") if not os.access(template / h, os.X_OK)]
    note = " (missing in ~/.git-templates/hooks: %s; new repos get no hooks)" % ", ".join(missing) if missing else ""
    hooks_path = _git(Path.home(), "config", "--global", "--get", "core.hooksPath")
    if not missing and not _template_dir_set(template.parent):
        note = " (git init.templateDir does not point at ~/.git-templates; new repos get no hooks)"
    elif not missing and os.environ.get("GIT_TEMPLATE_DIR"):
        note = " (GIT_TEMPLATE_DIR is set and takes the place of ~/.git-templates; new repos get no hooks)"
    if hooks_path is not None and hooks_path.returncode == 0 and hooks_path.stdout.strip():
        note = " (git core.hooksPath is %s, so git runs the hooks there and not the ones in each repo)" % hooks_path.stdout.strip()
    lines.append("  %-4s git template hooks%s" % ("ok" if not note else "--", note))
    zshrc = Path(os.environ.get("ZDOTDIR") or Path.home()) / ".zshrc"
    has_trigger = any("shell/harness.zsh" in line.split("#", 1)[0] for line in _read_home(zshrc).splitlines())
    lines.append("  %-4s zsh cd trigger%s" % ("ok" if has_trigger else "--", "" if has_trigger else " (not in %s; only Claude Code and git trigger setup)" % zshrc))
    fb = generate.find_fieldbook()
    lines.append("  %-4s fieldbook binary%s" % ("ok" if fb else "--", "" if fb else " (project memory is skipped without it)"))
    if harness_off():
        lines.append("  --   engine is switched off (~/.ai-rules/harness.off)")
    return lines, failed
