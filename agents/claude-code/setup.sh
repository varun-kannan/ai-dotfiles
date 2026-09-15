#!/usr/bin/env bash
# Claude Code extras beyond rules and skills: write hooks, settings, permissions.
# Called by install.sh with AGENT_DIR (this folder) exported.
set -euo pipefail

mkdir -p "$HOME/.claude/hooks"
install -m 0755 "$AGENT_DIR/hooks/pre-write-guard.sh"  "$HOME/.claude/hooks/pre-write-guard.sh"
install -m 0755 "$AGENT_DIR/hooks/post-write-audit.sh" "$HOME/.claude/hooks/post-write-audit.sh"

python3 - "$HOME/.claude/settings.json" "$HOME/.claude" <<'PY'
import json, os, sys
path, dest = sys.argv[1], sys.argv[2]
try:
    with open(path) as fh:
        cfg = json.load(fh)
except (IOError, ValueError):
    cfg = {}

cfg["includeCoAuthoredBy"] = False

# Skills must be able to open their own reference files. Without this a headless
# run (claude -p, automation) is denied the read and answers from the summary.
allow = cfg.setdefault("permissions", {}).setdefault("allow", [])
for rule in ["Read(~/.claude/skills/**)"]:
    if rule not in allow:
        allow.append(rule)

hooks = cfg.setdefault("hooks", {})
for event, matcher, script, timeout in [
    ("PreToolUse",  "Write|Edit|NotebookEdit", "pre-write-guard.sh",  15),
    ("PostToolUse", "Write|Edit",              "post-write-audit.sh", 20),
]:
    cmd = os.path.join(dest, "hooks", script)
    groups = hooks.setdefault(event, [])
    groups[:] = [g for g in groups
                 if not any(script in (h.get("command") or "") for h in g.get("hooks", []))]
    groups.append({"matcher": matcher,
                   "hooks": [{"type": "command", "command": cmd, "timeout": timeout}]})

with open(path, "w") as fh:
    json.dump(cfg, fh, indent=2)
    fh.write("\n")
PY
echo "  ok    hooks, settings.json (hooks, Read(~/.claude/skills/**), attribution flag)"
