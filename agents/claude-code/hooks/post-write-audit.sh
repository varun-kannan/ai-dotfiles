#!/usr/bin/env bash
# post-write-audit.sh - Claude Code PostToolUse hook for Write|Edit.
#
# Advisory. Reports imports that are not declared in the project's manifests, so
# a hallucinated package is questioned before it reaches a branch. Never blocks:
# monorepo aliases and transitive imports make false positives normal.
#
# CLAUDE.md section 6.

set -uo pipefail

CHECKDEPS="${CHECK_DEPS_BIN:-$HOME/.ai-rules/bin/check-deps}"
[ -x "$CHECKDEPS" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input="$(cat)"
path="$(jq -r '.tool_input.file_path // ""' <<<"$input")"
[ -f "$path" ] || exit 0

case "$path" in
  *.py|*.pyi|*.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs) ;;
  *) exit 0 ;;
esac

report="$("$CHECKDEPS" "$path" 2>/dev/null)"
[ -z "$report" ] && exit 0

jq -n --arg r "$report" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: ("Dependency check - unresolved imports were just written.\n\n" + $r + "\n\nVerify each package actually exists before continuing. If you cannot confirm it, do not import it - say so instead. Unresolvable AI-invented package names are an active supply-chain attack surface (slopsquatting).")
  }
}'
exit 0
