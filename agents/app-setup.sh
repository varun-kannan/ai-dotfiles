#!/usr/bin/env bash
# Chat apps take instructions through account settings, not a file the app reads.
# This prints the paste step. When RULES_FILE is set, the installer has also written
# a local copy there for reference; the app itself does not read it.
set -euo pipefail
. "$AGENT_DIR/agent.env"

src="$(cd "$AGENT_DIR/../.." && pwd)/rules/paste-into-chat-ui.txt"
chars=$(sed -n '3,$p' "$src" | wc -c | tr -d ' ')
echo "  manual  $APP_NAME reads instructions from account settings. Paste once per account:"
echo "          text:  everything below the marker line in rules/paste-into-chat-ui.txt ($chars chars)"
echo "          where: $APP_SETTINGS"
echo "          copy:  sed -n '3,\$p' '$src' | pbcopy"
if [ -n "${RULES_FILE:-}" ] && [ -f "$RULES_FILE" ]; then
  echo "  note    a local reference copy is at $RULES_FILE (the app does not read it)"
fi
