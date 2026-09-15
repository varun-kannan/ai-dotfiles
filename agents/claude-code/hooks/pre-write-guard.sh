#!/usr/bin/env bash
# hygiene:ignore-file - quotes the patterns it documents
# pre-write-guard.sh - Claude Code PreToolUse hook for Write|Edit|NotebookEdit.
#
# Blocks a write when the content carries a hard hygiene violation: invisible
# Unicode, curly quotes or em dashes in source code, unfilled placeholders,
# elided code, or leaked generation scaffolding.
#
# Exit 2 prevents the tool call and feeds stderr back to the model, so it gets
# one chance to fix the content instead of the defect landing on disk.
#
# CLAUDE.md sections 8, 11, 12.

set -uo pipefail

HYGIENE="${CONTENT_HYGIENE_BIN:-$HOME/.ai-rules/bin/content-hygiene}"
[ -x "$HYGIENE" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

input="$(cat)"

path="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // ""' <<<"$input")"

# Write uses content/file_text; Edit uses new_string; NotebookEdit uses new_source.
body="$(jq -r '
  .tool_input as $i
  | ($i.content // $i.file_text // $i.new_string // $i.new_str // $i.new_source // "")
' <<<"$input")"

[ -z "$body" ] && exit 0

# Never police the hygiene tooling, the forensics reference material, or anything
# explicitly opted out - all three legitimately contain the characters scanned for.
case "$path" in
  */.trash-preview/*|*/reference/forensics-*|*content-hygiene*|*pre-write-guard*|*post-write-audit*)
    exit 0 ;;
esac

name="$(basename "${path:-stdin.txt}")"
report="$("$HYGIENE" --stdin --name "$name" --quiet <<<"$body" 2>/dev/null)"

if [ -n "$report" ]; then
  {
    echo "Blocked: content-hygiene violations in ${path:-this content}."
    echo
    echo "$report"
    echo
    echo "Fix and retry:"
    echo "  - Invisible or non-ASCII characters: replace with plain ASCII."
    echo "    Straight quotes, '-' not em dash, '...' not the ellipsis character."
    echo "  - Placeholders and elided code: write the actual implementation."
    echo "    Never ship '... rest of the code' or 'your code here'."
    echo "  - Scaffolding: deliver the artifact, not the conversation around it."
    echo
    echo "If a character is genuinely required (test fixture, reference material),"
    echo "put the marker  hygiene:ignore-file  in the first 30 lines."
  } >&2
  exit 2
fi
exit 0
