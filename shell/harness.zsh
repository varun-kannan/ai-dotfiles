# ai-dotfiles: keep the project harness current when you cd into a project.
# Runs in the background with a fixed system PATH and prints nothing, so the prompt
# never waits on it and nothing in the folder can stand in for python3. The harness
# itself leaves the folder before doing any work.
_ai_harness_chpwd() {
  local h="${AI_RULES_HOME:-$HOME/.ai-rules}/bin/harness"
  [ -x "$h" ] || return 0
  ( PATH=/usr/bin:/bin:/usr/sbin:/sbin "$h" auto --trigger cd --cwd "$PWD" >/dev/null 2>&1 & )
}
autoload -Uz add-zsh-hook && add-zsh-hook chpwd _ai_harness_chpwd
