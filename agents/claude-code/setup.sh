#!/usr/bin/env bash
# Claude Code extras beyond rules and skills: write hooks, settings, permissions,
# subagents and slash commands. Called by install.sh with AGENT_DIR (this folder)
# and PYTHON (absolute python3) exported.
set -euo pipefail
SRC="$(cd "$AGENT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-$(command -v python3)}"

mkdir -p "$HOME/.claude/hooks"
for f in pre-write-guard.sh post-write-audit.sh prompt-route.py session-start.py; do
  install -m 0755 "$AGENT_DIR/hooks/$f" "$HOME/.claude/hooks/$f"
done

# Subagents (agents/definitions) and slash commands (commands/) are copied, not
# linked, so a re-run replaces them. A same-named file you wrote yourself is overwritten.
mkdir -p "$HOME/.claude/agents" "$HOME/.claude/commands"
for f in "$SRC"/agents/definitions/*.md; do
  install -m 0644 "$f" "$HOME/.claude/agents/$(basename "$f")"
done
for f in "$SRC"/commands/*.md; do
  install -m 0644 "$f" "$HOME/.claude/commands/$(basename "$f")"
done
echo "  ok    subagents: $(ls "$SRC"/agents/definitions/*.md | wc -l | tr -d ' '), commands: $(ls "$SRC"/commands/*.md | wc -l | tr -d ' ')"

"$PYTHON" -I - "$HOME/.claude/settings.json" "$HOME/.claude" "$PYTHON" <<'PY'
import json, os, re, shlex, sys, time
path, dest, python = sys.argv[1], sys.argv[2], sys.argv[3]

def leave(why):
    """The file is not ours to rewrite as it stands: say so, change nothing, and fail this agent."""
    print("  fail  %s: %s. Left untouched, so the hooks are NOT registered. Fix it and re-run install.sh."
          % (path, why), file=sys.stderr)
    sys.exit(1)


class Duplicate(Exception):
    pass


def unique_keys(pairs):
    """json keeps only the last of two equal keys; rewriting the file would drop the others."""
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise Duplicate(key)
        seen.add(key)
    return dict(pairs)


class Number:
    """A decimal number as the file spells it: a float round trip would turn 1.10 into 1.1."""

    def __init__(self, text):
        self.text = text


def dump(value, level=0):
    """json.dumps(indent=2) with numbers kept as written and non-ASCII text kept as it is."""
    pad, inner = "\n" + "  " * level, "\n" + "  " * (level + 1)
    if isinstance(value, Number):
        return value.text
    if isinstance(value, dict):
        items = ["%s: %s" % (dump(k), dump(v, level + 1)) for k, v in value.items()]
        return "{" + inner + ("," + inner).join(items) + pad + "}" if items else "{}"
    if isinstance(value, list):
        items = [dump(v, level + 1) for v in value]
        return "[" + inner + ("," + inner).join(items) + pad + "]" if items else "[]"
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = json.dumps(value)          # a lone surrogate escape cannot be written as UTF-8
    return text


# Write through a symlinked settings.json (a dotfiles setup) instead of replacing the link.
path = os.path.realpath(path)
cfg = {}
if os.path.lexists(path):
    if not os.path.isfile(path):
        leave("not a regular file")
    if not os.access(path, os.R_OK | os.W_OK):
        leave("not readable and writable")
    try:
        with open(path, encoding="utf-8-sig") as fh:
            raw = fh.read()
        cfg = json.loads(raw, object_pairs_hook=unique_keys, parse_float=Number) if raw.strip() else {}
    except Duplicate as exc:
        leave("the key %s appears more than once in one object, and only the last would be kept"
              % json.dumps(exc.args[0]))
    except (OSError, ValueError) as exc:
        leave("not valid JSON (%s; comments and trailing commas are not JSON)" % exc)
    if not isinstance(cfg, dict):
        leave("the top level is not a JSON object")
elif not os.path.isdir(os.path.dirname(path)):
    leave("its folder does not exist (a dangling link?)")

# A part of the file with an unexpected shape is yours, not ours to drop.
if "permissions" in cfg and not isinstance(cfg["permissions"], dict):
    leave('"permissions" is not an object')
if isinstance(cfg.get("permissions"), dict) and "allow" in cfg["permissions"] and not isinstance(cfg["permissions"]["allow"], list):
    leave('"permissions.allow" is not a list')
if "hooks" in cfg and not isinstance(cfg["hooks"], dict):
    leave('"hooks" is not an object')
for event in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart"):
    if isinstance(cfg.get("hooks"), dict) and event in cfg["hooks"] and not isinstance(cfg["hooks"][event], list):
        leave('"hooks.%s" is not a list' % event)

cfg["includeCoAuthoredBy"] = False

# Skills must be able to open their own reference files. Without this a headless
# run (claude -p, automation) is denied the read and answers from the summary.
perms = cfg.get("permissions", {})
allow = perms.get("allow", [])
for rule in ["Read(~/.claude/skills/**)"]:
    if rule not in allow:
        allow.append(rule)
perms["allow"] = allow
cfg["permissions"] = perms

hooks = cfg.get("hooks", {})


def ours(command, script_path):
    """True when the command is this exact script on its own, or an interpreter and the script,
    however its home folder is spelled. A command that wraps the script or passes it extra
    arguments was written by the user and is kept."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) == 2 and re.fullmatch(r"(ba|z)?sh|python(\d+(\.\d+)?)?", os.path.basename(parts[0])):
        parts = parts[1:]
    if len(parts) != 1:
        return False
    want = os.path.realpath(os.path.normpath(script_path))
    return want == os.path.realpath(os.path.normpath(os.path.expanduser(os.path.expandvars(parts[0]))))


for event, matcher, script, timeout in [
    ("PreToolUse",  "Write|Edit|NotebookEdit", "pre-write-guard.sh",  15),
    ("PostToolUse", "Write|Edit",              "post-write-audit.sh", 20),
    ("UserPromptSubmit", None,                 "prompt-route.py",     10),  # no matcher support
    ("SessionStart", None,                     "session-start.py",    30),
]:
    script_path = os.path.join(dest, "hooks", script)
    # Python hooks run with the absolute interpreter, so a python3 planted in a repo
    # cannot be picked from PATH.
    command = ("%s %s" % (shlex.quote(python), shlex.quote(script_path)) if script.endswith(".py")
               else shlex.quote(script_path))
    groups = hooks.get(event, [])
    kept = []
    for group in groups:
        if not isinstance(group, dict):
            kept.append(group)
            continue
        entries = group.get("hooks") if isinstance(group.get("hooks"), list) else []
        rest = [h for h in entries if not (isinstance(h, dict) and isinstance(h.get("command"), str)
                                           and ours(h["command"], script_path))]
        if rest or not entries:
            kept.append(dict(group, hooks=rest) if entries else group)
    new = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
    if matcher:
        new["matcher"] = matcher
    kept.append(new)
    hooks[event] = kept
cfg["hooks"] = hooks

# settings.json can hold tokens: keep its mode, and default to private for a new file.
try:
    mode = os.stat(path).st_mode & 0o777
except OSError:
    mode = 0o600
try:
    text = dump(cfg) + "\n"
except ValueError:
    leave("it holds a number JSON cannot express (Infinity or NaN)")
tmp = "%s.%d.tmp" % (path, os.getpid())
# The new file is made next to the old one and swapped in, so its folder must be writable too:
# a writable file in a read-only folder (a linked dotfiles file, say) cannot be replaced.
try:
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
except OSError as exc:
    try:
        os.remove(tmp)
    except OSError:
        pass
    leave("cannot write a new copy in %s (%s)" % (os.path.dirname(path), exc.strerror or exc))
print("  ok    hooks (write guard, write audit, prompt-route, session-start), settings.json")
PY
