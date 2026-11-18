# ai-dotfiles: keep the project harness current when you cd into a project.
# Runs in the background and prints nothing, so the prompt never waits on it.
_ai_harness_chpwd() {
  [ -x "$HOME/.ai-rules/bin/harness" ] || return 0
  ( "$HOME/.ai-rules/bin/harness" auto --trigger cd --cwd "$PWD" >/dev/null 2>&1 & )
}
autoload -Uz add-zsh-hook && add-zsh-hook chpwd _ai_harness_chpwd
