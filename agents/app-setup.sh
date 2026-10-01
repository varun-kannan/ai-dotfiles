#!/usr/bin/env bash
# For apps where instructions live in account settings (not a file), print the paste step.
# For apps with a file at RULES_FILE, it's already installed.
set -euo pipefail
. "$AGENT_DIR/agent.env"

if [ -z "$RULES_FILE" ]; then
  # No file path: instructions are account-settings only
  src="$(cd "$AGENT_DIR/../.." && pwd)/rules/paste-into-chat-ui.txt"
  chars=$(sed -n '3,$p' "$src" | wc -c | tr -d ' ')
  echo "  manual  no config file exists for $APP_NAME. Paste once per account:"
  echo "          text:  everything below the marker line in rules/paste-into-chat-ui.txt ($chars chars)"
  echo "          where: $APP_SETTINGS"
  echo "          copy:  sed -n '3,\$p' '$src' | pbcopy"
elif [ -f "$RULES_FILE" ]; then
  # File exists: already installed
  echo "  ok      $APP_NAME rules installed at $RULES_FILE"
fi
