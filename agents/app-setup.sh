#!/usr/bin/env bash
# Shared by chat apps whose instructions live in account settings, not a file.
# Nothing can be written for them; print exactly what to paste and where.
set -euo pipefail
. "$AGENT_DIR/agent.env"
src="$(cd "$AGENT_DIR/../.." && pwd)/rules/paste-into-chat-ui.txt"
chars=$(sed -n '3,$p' "$src" | wc -c | tr -d ' ')
echo "  manual  no config file exists for $APP_NAME. Paste once per account:"
echo "          text:  everything below the marker line in rules/paste-into-chat-ui.txt ($chars chars)"
echo "          where: $APP_SETTINGS"
echo "          copy:  sed -n '3,\$p' '$src' | pbcopy"
