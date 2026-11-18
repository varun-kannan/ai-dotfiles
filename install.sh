#!/usr/bin/env bash
# install.sh - install shared rules, tooling, skills and git hooks for every
# AI agent defined under agents/. Idempotent; re-run after any edit.
#
#   ./install.sh                        install for every detected agent
#   ./install.sh --existing-repos DIR   also put the git hooks in repos under DIR

set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED="$HOME/.ai-rules"

echo "source: $SRC"

# Shared tooling and the canonical rules copy.
echo
echo "shared -> $SHARED"
rm -rf "$SHARED/bin" && mkdir -p "$SHARED/bin"   # rebuilt so removed tools do not linger
install -m 0755 "$SRC"/bin/* "$SHARED/bin/"
install -m 0644 "$SRC/rules/RULES.md" "$SHARED/RULES.md"
# Generated copies the bin/ tools read. Rebuilt on every run.
rm -rf "$SHARED/rules" "$SHARED/config" "$SHARED/skills" "$SHARED/agents" "$SHARED/engine" "$SHARED/shell"
cp -R "$SRC/rules" "$SRC/config" "$SRC/skills" "$SRC/engine" "$SRC/shell" "$SHARED/"
find "$SHARED/engine" -name __pycache__ -type d -prune -exec rm -rf {} +
mkdir -p "$SHARED/agents" && cp -R "$SRC/agents/definitions" "$SHARED/agents/"
echo "  ok    bin/, RULES.md, rules/, config/, skills/, engine/, shell/, agents/definitions/"

# The engine re-runs this script when the repo has a new clean commit, so it
# records where the repo is and which commit is installed.
printf '%s\n' "$SRC" > "$SHARED/source"
if [ -z "$(git -C "$SRC" status --porcelain 2>/dev/null)" ]; then
  git -C "$SRC" rev-parse HEAD > "$SHARED/installed-commit" 2>/dev/null || true
else
  echo "uncommitted" > "$SHARED/installed-commit"
fi

# Projects the engine must never set up. Yours to edit; never overwritten.
if [ ! -e "$SHARED/harness-exclude" ]; then
  cat > "$SHARED/harness-exclude" <<'EOT'
# One path or glob per line. The engine never sets up these projects or anything under them.
# A .harness-skip file inside a project does the same for that project alone.
EOT
  echo "  new   harness-exclude"
fi
# The engine must not generate files into its own source repo.
grep -qxF "$SRC" "$SHARED/harness-exclude" || printf '%s\n' "$SRC" >> "$SHARED/harness-exclude"

# cd trigger for terminal tools. One marked block in ~/.zshrc, rewritten in place.
if [ -n "${ZDOTDIR:-}" ]; then ZSHRC="$ZDOTDIR/.zshrc"; else ZSHRC="$HOME/.zshrc"; fi
if ! grep -q 'BEGIN ai-dotfiles:harness' "$ZSHRC" 2>/dev/null; then
  printf '\n# BEGIN ai-dotfiles:harness\n[ -r "$HOME/.ai-rules/shell/harness.zsh" ] && . "$HOME/.ai-rules/shell/harness.zsh"\n# END ai-dotfiles:harness\n' >> "$ZSHRC"
  echo "  add   cd trigger in $ZSHRC (new terminals pick it up)"
else
  echo "  keep  cd trigger in $ZSHRC"
fi

write_rules() {  # $1 destination, $2 title
  mkdir -p "$(dirname "$1")"
  if [ -s "$1" ] && ! grep -q 'Behavioral guidelines to reduce common LLM mistakes' "$1"; then
    cp "$1" "$1.bak"
    echo "  note  existing $(basename "$1") backed up to $(basename "$1").bak"
  fi
  { echo "# $2"; tail -n +2 "$SRC/rules/RULES.md"; } > "$1"
}

# Every agents/<name>/agent.env is one agent. Add a folder to add an agent.
# setup.sh in that folder, if executable, runs after rules and skills.
for env in "$SRC"/agents/*/agent.env; do
  AGENT_DIR="$(dirname "$env")"
  name="$(basename "$AGENT_DIR")"
  DETECT="" RULES_FILE="" RULES_TITLE="" SKILLS_DIR=""
  # shellcheck disable=SC1090
  . "$env"

  echo
  # Empty DETECT installs unconditionally, so the rules are in place before the tool is.
  if [ -n "$DETECT" ] && [ ! -e "$DETECT" ]; then
    echo "$name: not installed ($DETECT missing), skipped"
    continue
  fi
  echo "$name${DETECT:+ -> $DETECT}"

  if [ -n "$RULES_FILE" ]; then
    write_rules "$RULES_FILE" "${RULES_TITLE:-Rules}"
    echo "  ok    $RULES_FILE"
  fi

  if [ -n "$SKILLS_DIR" ]; then
    mkdir -p "$SKILLS_DIR"
    for skill in "$SRC"/skills/*/; do
      [ -f "$skill/SKILL.md" ] || continue
      s="$(basename "$skill")"
      rm -rf "${SKILLS_DIR:?}/$s"
      cp -R "$skill" "$SKILLS_DIR/$s"
      echo "  ok    skill $s"
    done
  fi

  if [ -x "$AGENT_DIR/setup.sh" ]; then
    AGENT_DIR="$AGENT_DIR" "$AGENT_DIR/setup.sh"
  fi
done

# Git layer: catches output from every tool, configured or not.
echo
echo "git hooks -> ~/.git-templates (applies to new inits and clones)"
mkdir -p "$HOME/.git-templates/hooks"
install -m 0755 "$SRC"/hooks/git/* "$HOME/.git-templates/hooks/"
git config --global init.templateDir "$HOME/.git-templates"
echo "  ok    $(ls "$SRC/hooks/git" | tr '\n' ' ')"

if [ "${1:-}" = "--existing-repos" ]; then
  root="${2:-$HOME}"
  echo
  echo "existing repos under $root"
  find "$root" -maxdepth 4 -type d -name .git 2>/dev/null | while read -r g; do
    install -m 0755 "$SRC"/hooks/git/* "$g/hooks/"
    echo "  hooked ${g%/.git}"
  done
fi

echo
echo "done"
