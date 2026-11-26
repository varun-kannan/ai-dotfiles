#!/bin/bash
# post-write-audit.sh - Claude Code PostToolUse hook for Write|Edit.
#
# Advisory. Reports imports that are not declared in the project's manifests, so
# a hallucinated package is questioned before it reaches a branch. Never blocks:
# monorepo aliases and transitive imports make false positives normal.
#
# CLAUDE.md section 6.

set -uo pipefail

# Only absolute PATH entries: an empty or relative one could pick up a program from the repo.
_p=""; _ifs="$IFS"; IFS=:
for _d in $PATH; do case "$_d" in /*) _p="${_p:+$_p:}$_d" ;; esac; done
IFS="$_ifs"; PATH="${_p:-/usr/bin:/bin}"; export PATH

CHECKDEPS="${CHECK_DEPS_BIN:-${AI_RULES_HOME:-$HOME/.ai-rules}/bin/check-deps}"
[ -x "$CHECKDEPS" ] || exit 0

# python3 reads and writes the hook JSON, so the audit does not depend on jq.
input="$(cat)"
cd / 2>/dev/null || exit 0    # hooks start in the project folder, which may hold look-alike programs and modules
path="$(python3 -I -c '
import json, sys
try:
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") if isinstance(data, dict) else None
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    print(path if isinstance(path, str) else "")
except ValueError:
    pass
' <<<"$input")"
[ -f "$path" ] || exit 0

case "$path" in
  *.py|*.pyi|*.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs) ;;
  *) exit 0 ;;
esac

report="$("$CHECKDEPS" -- "$path" 2>/dev/null)"
[ -z "$report" ] && exit 0

REPORT="$report" python3 -I -c '
import json, os
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
    "Dependency check - unresolved imports were just written.\n\n" + os.environ["REPORT"] +
    "\n\nVerify each package actually exists before continuing. If you cannot confirm it, do not import it - say so instead. "
    "Unresolvable AI-invented package names are an active supply-chain attack surface (slopsquatting)."}}))
'
exit 0
