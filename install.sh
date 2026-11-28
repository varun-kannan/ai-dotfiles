#!/usr/bin/env bash
# install.sh - install shared rules, tooling, skills, the project engine and git hooks
# for every AI agent defined under agents/. Idempotent; re-run after any edit.
#
#   ./install.sh                        install for every detected agent
#   ./install.sh --existing-repos DIR   also put the git hooks in repos under DIR
#   ./install.sh --help
#
# Everything runs inside main(), so bash has read the whole script before the first
# command runs: a git pull during a background self-update cannot change it mid-run.
# Exit: 0 installed; 1 something was not installed (named at the end); 2 usage error.

set -euo pipefail

if [ -z "${HOME:-}" ]; then
  echo "HOME is not set" >&2
  exit 1
fi
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHARED="${AI_RULES_HOME:-$HOME/.ai-rules}"
LOCK="$SHARED/.install.lock"
STAGE=""
GOT_LOCK=0
LOCK_ID=""
FAILED_AGENTS=""
FAILED_STEPS=""
# New hooks have a typed marker; the remaining alternatives identify hooks from older installs.
TYPED_HOOK='^# ai-dotfiles hook: (applypatch-msg|commit-msg|post-checkout|post-merge|pre-applypatch|pre-commit)$'
LEGACY_HOOK='^# (ai-dotfiles-hook:|strip-ai-attribution - git commit-msg hook|pre-commit - universal output-hygiene gate|Keeps the project harness current)'
LINKED="bin engine rules config skills shell agents RULES.md"
# Only these are copied from bin/, so a stray file there (a patch reject, an editor backup) never
# ships as a command.
TOOLS="check-deps content-hygiene context-manager.py harness"

cleanup() {
  [ -n "$STAGE" ] && rm -rf "$STAGE"
  if [ "$GOT_LOCK" = 1 ] && [ "$(readlink "$LOCK" 2>/dev/null)" = "$LOCK_ID" ]; then
    rm -f "$LOCK"
  fi
  return 0
}

# One install at a time. The lock is a symlink whose target is the owner's pid and start
# time, so taking it and naming its owner are one atomic step. A lock whose owner is gone is cleared.
start_time() {  # $1 pid: when it started, without spaces, or nothing
  LC_ALL=C ps -o lstart= -p "$1" 2>/dev/null | tr -d ' ' || true
}

legacy_lock_owner() {  # $1 pid: an older installer wrote only its pid
  local command
  command="$(ps -p "$1" -o command= 2>/dev/null || true)"
  # If process inspection is denied, a live owner's lock is safer to keep until it times out.
  [ -n "$command" ] || return 0
  case "$command" in
    install.sh|install.sh\ *|*/install.sh|*/install.sh\ *) return 0 ;;
    *sh\ install.sh|*sh\ install.sh\ *|*sh\ */install.sh|*sh\ */install.sh\ *) return 0 ;;
  esac
  return 1
}

take_lock() {
  local i raw pid="" since wait="${AI_INSTALL_LOCK_WAIT:-60}"
  case "$wait" in ''|*[!0-9]*) wait=60 ;; esac
  [ "$wait" -ge 1 ] || wait=1
  if ! mkdir -p "$SHARED" 2>/dev/null || [ ! -w "$SHARED" ]; then
    echo "cannot write to $SHARED" >&2
    return 1
  fi
  LOCK_ID="$$:$(start_time $$)"
  [ "$LOCK_ID" = "$$:" ] && LOCK_ID="$$"
  for i in $(seq 1 "$wait"); do
    # os.symlink fails if anything is already there; ln -s would create a link inside a folder.
    if "$PYTHON" -I -c 'import os, sys; os.symlink(sys.argv[2], sys.argv[1])' "$LOCK" "$LOCK_ID" 2>/dev/null; then
      GOT_LOCK=1
      return 0
    fi
    if [ -d "$LOCK" ] && [ ! -L "$LOCK" ]; then
      raw="$(cat "$LOCK/pid" 2>/dev/null || true)"        # lock folder of an older installer
    else
      raw="$(readlink "$LOCK" 2>/dev/null || true)"
    fi
    pid="${raw%%:*}"
    since=""
    case "$raw" in *:*) since="${raw#*:}" ;; esac
    case "$pid" in ''|*[!0-9]*) pid="" ;; esac
    # A pid can be reused by another program after a crash. With a start time it only counts
    # when that same process still runs. The invoking parent cannot be a separate installer;
    # for an older pid-only lock, the command line must run this installer.
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null \
       || [ "$pid" = "$PPID" ] \
       || { [ -n "$since" ] && [ "$(start_time "$pid")" != "$since" ]; } \
       || { [ -z "$since" ] && ! legacy_lock_owner "$pid"; }; then
      # Not a live installer's lock. Waiters clearing a lock take turns through a second lock,
      # and only they remove a lock whose owner is gone, so the lock read again under it is still
      # the one just read when it is removed: a newer live lock is never moved or put back.
      if "$PYTHON" -I -c '
import os, shutil, sys, time
lock, raw, turn = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    os.symlink(str(os.getpid()), turn)
except OSError:
    # A turn this old was left by a waiter killed inside this short step. Between looking and
    # removing, another waiter can clear it and a third take a fresh one, so it is moved aside
    # first and deleted only if what moved is the old turn looked at; a live one is linked back.
    try:
        old = os.lstat(turn)
        if time.time() - old.st_mtime > 30:
            aside = "%s.%d.stale" % (turn, os.getpid())
            os.rename(turn, aside)
            moved = os.lstat(aside)
            try:
                if (moved.st_dev, moved.st_ino, moved.st_mtime) != (old.st_dev, old.st_ino, old.st_mtime):
                    os.link(aside, turn, follow_symlinks=False)  # fails, keeping a newer turn, if one is there
            finally:
                os.remove(aside)
    except (OSError, NotImplementedError):
        pass
    sys.exit(1)
try:
    if os.path.islink(lock):
        seen = os.readlink(lock)
    else:
        try:
            with open(os.path.join(lock, "pid")) as fh:
                seen = fh.read().strip()
        except OSError:
            seen = None
    if seen != raw:
        sys.exit(1)
    shutil.rmtree(lock) if os.path.isdir(lock) and not os.path.islink(lock) else os.remove(lock)
finally:
    os.remove(turn)
' "$LOCK" "$raw" "$LOCK.turn" 2>/dev/null \
         && "$PYTHON" -I -c 'import os, sys; os.symlink(sys.argv[2], sys.argv[1])' "$LOCK" "$LOCK_ID" 2>/dev/null; then
        GOT_LOCK=1                        # the stale lock is gone and this install holds it now
        return 0
      fi
    fi
    sleep 1
  done
  if [ -n "$pid" ]; then
    echo "another install (pid $pid) is still running; try again later" >&2
  else
    echo "could not take the install lock $LOCK; remove it and try again" >&2
  fi
  return 1
}

# Copy into a new release folder, then flip one symlink, so the engine, tools and
# rules always change together and a trigger never sees half of an install.
install_release() {
  local id rel name old extra prev linkfail=""
  id="$(date +%Y%m%d%H%M%S)-$$"
  if [ -e "$SHARED/current" ] && [ ! -L "$SHARED/current" ]; then
    echo "$SHARED/current is not a link. Move it away and run the installer again." >&2
    return 1
  fi
  # This function is called as `install_release || rc=$?`, where bash switches off `set -e`,
  # so every step is checked by hand: a release that is not whole must never become current.
  mkdir -p "$SHARED/releases" || return 1
  # Half-made stages are removed after a day. An .old-layout-* folder is never removed by age: it
  # can hold files of yours from an upgrade that stopped half way.
  find "$SHARED/releases" -maxdepth 1 -name '.stage-*' -mtime +0 -exec rm -rf {} + 2>/dev/null || true
  STAGE="$SHARED/releases/.stage-$id"
  rel="$SHARED/releases/$id"
  if ! mkdir "$STAGE" 2>/dev/null; then
    echo "  fail  cannot write to $SHARED/releases" >&2
    return 1
  fi
  mkdir -p "$STAGE/bin" "$STAGE/agents" || return 1
  for name in $TOOLS; do
    install -m 0755 "$SRC/bin/$name" "$STAGE/bin/$name" || return 1
  done
  cp -R "$SRC/engine" "$SRC/rules" "$SRC/config" "$SRC/skills" "$SRC/shell" "$STAGE/" || return 1
  cp -R "$SRC/agents/definitions" "$STAGE/agents/" || return 1
  cp "$SRC/rules/RULES.md" "$STAGE/RULES.md" || return 1
  find "$STAGE" \( -name __pycache__ -o -name .DS_Store \) -prune -exec rm -rf {} + || return 1
  # Every file of the source must be in the copy, byte for byte, before it can become current.
  "$PYTHON" -I -c '
import filecmp, os, sys
src, stage, tools = sys.argv[1], sys.argv[2], sys.argv[3].split()
for t in tools:
    there = os.path.join(stage, "bin", t)
    if not os.path.isfile(there) or not filecmp.cmp(os.path.join(src, "bin", t), there, shallow=False):
        sys.exit("incomplete copy: bin/%s" % t)
pairs = [("engine", "engine"), ("rules", "rules"), ("config", "config"), ("skills", "skills"),
         ("shell", "shell"), ("agents/definitions", "agents/definitions")]
if not filecmp.cmp(os.path.join(src, "rules", "RULES.md"), os.path.join(stage, "RULES.md"), shallow=False):
    sys.exit("incomplete copy: RULES.md")
for a, b in pairs:
    for folder, dirs, files in os.walk(os.path.join(src, a)):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".pyc") or f == ".DS_Store":
                continue
            here = os.path.join(folder, f)
            there = os.path.join(stage, b, os.path.relpath(here, os.path.join(src, a)))
            if not os.path.isfile(there) or not filecmp.cmp(here, there, shallow=False):
                sys.exit("incomplete copy: %s" % there)
' "$SRC" "$STAGE" "$TOOLS" || return 1
  mv "$STAGE" "$rel" || return 1
  STAGE=""
  # Flip first. If this fails, the previous install is still whole.
  if ! "$PYTHON" -I -c 'import os, sys; t = sys.argv[1] + ".new"; os.path.lexists(t) and os.remove(t); os.symlink(sys.argv[2], t); os.replace(t, sys.argv[1])' \
    "$SHARED/current" "releases/$id" 2>/dev/null; then
    echo "  fail  could not switch $SHARED/current to the new release (is $SHARED/current.new in the way?)" >&2
    rm -rf "${rel:?}"
    return 1
  fi
  # Then point each name at the release. A real folder here is the old copy-in-place
  # layout: it is moved aside, replaced by the link, and only then deleted. A name that cannot
  # be switched is reported once the rest is done; what was moved aside is still sorted below.
  old="$SHARED/releases/.old-layout-$id"
  for name in $LINKED; do
    if [ -L "$SHARED/$name" ]; then
      prev="$(readlink "$SHARED/$name")"
      if [ "$prev" != "current/$name" ]; then
        # Nothing is lost by replacing a link, but one that was not ours (a link into your
        # dotfiles, say) should not vanish without a word.
        case "$prev" in
          current/*|releases/*) ;;
          *) echo "  note  $SHARED/$name was a link to $prev; it now points to current/$name" ;;
        esac
        ln -sfn "current/$name" "$SHARED/$name" || linkfail="$linkfail $name"
      fi
    elif [ -e "$SHARED/$name" ]; then
      { mkdir -p "$old" && mv "$SHARED/$name" "$old/$name" && ln -s "current/$name" "$SHARED/$name"; } || linkfail="$linkfail $name"
    else
      ln -s "current/$name" "$SHARED/$name" || linkfail="$linkfail $name"
    fi
  done
  # Files of yours that sat in the old folders (a script in bin/, a local config) are not
  # deleted with them: they are kept in a folder you are told about.
  if [ -d "$old" ]; then
    extra="$("$PYTHON" -I -c '
import os, sys
old, cur = sys.argv[1], sys.argv[2]
for folder, dirs, files in os.walk(old):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        rel = os.path.relpath(os.path.join(folder, f), old)
        here, there = os.path.join(folder, f), os.path.join(cur, rel)
        same = False
        try:
            with open(here, "rb") as a, open(there, "rb") as b:
                same = a.read() == b.read()
        except OSError:
            pass
        if f.endswith(".pyc") or f == ".DS_Store" or same:
            os.remove(here)                   # the release has the same file
        else:
            print(rel)                        # yours, or one you changed: kept
for folder, dirs, files in os.walk(old, topdown=False):
    if folder != old and not os.listdir(folder):
        os.rmdir(folder)
' "$old" "$SHARED/current")" || extra="?"
    if [ -n "$extra" ] && ! mv "$old" "$SHARED/kept-from-old-layout-$id"; then
      echo "  note  files of yours from the old layout were kept in $old:" >&2
      printf '%s\n' "$extra" | sed 's/^/          /' >&2
    elif [ -n "$extra" ]; then
      echo "  note  files of yours from the old layout were kept in $SHARED/kept-from-old-layout-$id:"
      printf '%s\n' "$extra" | sed 's/^/          /'
    else
      rm -rf "$old"
    fi
  fi
  if [ -n "$linkfail" ]; then
    echo "  FAIL  release $id is current, but these could not be switched to it:$linkfail" >&2
    return 2
  fi
  # Keep the newest three releases.
  ls -1 "$SHARED/releases" | awk '!/^\./' | sort | awk '{a[NR]=$0} END {for (i = 1; i <= NR - 3; i++) print a[i]}' |
    while IFS= read -r old; do
      [ "$old" = "$id" ] || rm -rf "${SHARED:?}/releases/$old"
    done
  echo "  ok    release $id: bin/, engine/, rules/, config/, skills/, shell/, agents/definitions/, RULES.md"
}

record_source() {
  printf '%s\n' "$SRC" 2>/dev/null > "$SHARED/source" || return 1
  if ! command -v git >/dev/null 2>&1; then
    echo "uncommitted" > "$SHARED/installed-commit" || return 1
    echo "  note  git was not found: automatic updates stay off"
  elif [ -z "$(git --no-optional-locks -C "$SRC" status --porcelain 2>/dev/null || echo dirty)" ] \
     && git -C "$SRC" rev-parse HEAD > "$SHARED/installed-commit.new" 2>/dev/null; then
    mv "$SHARED/installed-commit.new" "$SHARED/installed-commit" || return 1
  else
    rm -f "$SHARED/installed-commit.new"
    echo "uncommitted" > "$SHARED/installed-commit" || return 1
    echo "  note  installed from uncommitted changes: automatic updates stay off until a clean ./install.sh"
  fi
  git -C "$SRC" symbolic-ref --short HEAD > "$SHARED/installed-branch" 2>/dev/null || echo "detached" > "$SHARED/installed-branch"
  if [ -x "$HOME/.fieldbook/bin/fieldbook" ]; then
    printf '%s\n' "$HOME/.fieldbook/bin/fieldbook" > "$SHARED/fieldbook-path" || return 1
  else
    rm -f "$SHARED/fieldbook-path"
  fi
}

seed_user_files() {
  if [ ! -e "$SHARED/harness-exclude" ]; then
    cat > "$SHARED/harness-exclude" <<'EOT'
# One path or glob per line. The engine never sets up these projects or anything under them.
# A .harness-skip file inside a project does the same for that project alone.
EOT
    echo "  new   harness-exclude"
  fi
  grep -qxF "$SRC" "$SHARED/harness-exclude" 2>/dev/null || printf '%s\n' "$SRC" 2>/dev/null >> "$SHARED/harness-exclude" || return 1
}

zsh_trigger() {
  local target="$HOME/.zshrc"
  [ -n "${ZDOTDIR:-}" ] && target="$ZDOTDIR/.zshrc"
  # Present only when the file zsh reads holds the line that loads the trigger.
  if grep -q 'BEGIN ai-dotfiles:harness' "$target" 2>/dev/null && grep -q '^[^#]*shell/harness\.zsh' "$target" 2>/dev/null; then
    echo "  keep  cd trigger in $target"
    return 0
  fi
  if { printf '\n# BEGIN ai-dotfiles:harness\n[ -r "${AI_RULES_HOME:-$HOME/.ai-rules}/shell/harness.zsh" ] && . "${AI_RULES_HOME:-$HOME/.ai-rules}/shell/harness.zsh"\n# END ai-dotfiles:harness\n' >> "$target"; } 2>/dev/null; then
    echo "  add   cd trigger in $target (new terminals pick it up)"
  else
    echo "  warn  could not write $target; the cd trigger is not installed" >&2
    return 1
  fi
}

# Rules files are generated. One whose content still matches what the last install wrote
# is replaced quietly; one that was edited, or that this installer has no record of
# writing, is first kept as <file>.bak-<time>. Writing goes through the path, so a
# symlinked rules file keeps its link and its mode. Returns 1 when the file cannot be written.
write_rules() {  # $1 destination, $2 title
  local dest="$1" new key old_sum cur_sum last
  if [ "$dest" -ef "$SRC/rules/RULES.md" ]; then
    echo "  keep  $(basename "$dest") is a link to this repo's rules/RULES.md"
    return 0
  fi
  mkdir -p "$(dirname "$dest")" "$SHARED/generated" 2>/dev/null || return 1
  new="$(mktemp)" || return 1
  { echo "# $2"; tail -n +2 "$SRC/rules/RULES.md"; } > "$new"
  key="$SHARED/generated/$(printf '%s' "$dest" | shasum | cut -c1-16)"
  if [ -s "$dest" ] && ! cmp -s "$dest" "$new"; then
    old_sum="$(cat "$key" 2>/dev/null || true)"
    cur_sum="$(shasum < "$dest" | cut -c1-40)"
    if [ "$old_sum" != "$cur_sum" ]; then
      last="$(ls -1t "$dest".bak-* 2>/dev/null | head -n 1)"
      if [ -n "$last" ] && cmp -s "$last" "$dest"; then
        :                                 # this very content is already kept from an earlier run
      elif ! cp "$dest" "$dest.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null; then
        rm -f "$new"
        return 1
      fi
      if [ -z "$old_sum" ]; then
        echo "  note  $(basename "$dest") existed before this installer kept records; previous copy kept as $(basename "$dest").bak-<time>"
      else
        echo "  note  $(basename "$dest") had changes the installer did not write; kept as $(basename "$dest").bak-<time>"
      fi
    fi
  fi
  if ! cat "$new" 2>/dev/null > "$dest"; then
    rm -f "$new"
    return 1
  fi
  shasum < "$new" | cut -c1-40 > "$key"
  rm -f "$new"
}

# One agent. Every step is checked, so a failure here is reported and the install goes on
# with the next agent instead of stopping half way.
install_agent() {  # $1 agent folder
  local AGENT_DIR="$1" name skill s list
  name="$(basename "$AGENT_DIR")"
  DETECT="" RULES_FILE="" RULES_TITLE="" SKILLS_DIR=""
  # shellcheck disable=SC1090
  . "$AGENT_DIR/agent.env" || return 1
  echo
  # Empty DETECT installs unconditionally, so the rules are in place before the tool is.
  if [ -n "$DETECT" ] && [ ! -e "$DETECT" ]; then
    echo "$name: not installed ($DETECT missing), skipped"
    return 0
  fi
  echo "$name${DETECT:+ -> $DETECT}"
  local rules_failed=0
  if [ -n "$RULES_FILE" ]; then
    # A rules file that cannot be written is reported, and the rest of this agent (skills,
    # hooks, settings) is still installed.
    if write_rules "$RULES_FILE" "${RULES_TITLE:-Rules}"; then
      echo "  ok    $RULES_FILE"
    else
      echo "  fail  could not write $RULES_FILE" >&2
      rules_failed=1
    fi
  fi
  if [ -n "$SKILLS_DIR" ] && [ "$SKILLS_DIR" -ef "$SRC/skills" ]; then
    echo "  keep  skills: $SKILLS_DIR is this repo's own skills folder"
  elif [ -n "$SKILLS_DIR" ]; then
    mkdir -p "$SKILLS_DIR" 2>/dev/null || { echo "  fail  could not create $SKILLS_DIR" >&2; return 1; }
    # A skill folder is replaced whole. One that an earlier install put here and the repo no
    # longer has is removed; a skill of your own with another name is never touched.
    list="$SHARED/generated/skills-$(printf '%s' "$SKILLS_DIR" | shasum | cut -c1-16)"
    mkdir -p "$SHARED/generated" 2>/dev/null || return 1
    : > "$list.new" || return 1
    for skill in "$SRC"/skills/*/; do
      [ -f "$skill/SKILL.md" ] || continue
      s="$(basename "$skill")"
      rm -rf "${SKILLS_DIR:?}/$s" 2>/dev/null && cp -R "$skill" "$SKILLS_DIR/$s" 2>/dev/null \
        || { echo "  fail  could not copy skill $s to $SKILLS_DIR" >&2; return 1; }
      printf '%s\n' "$s" >> "$list.new"
    done
    if [ -f "$list" ]; then
      while IFS= read -r s; do
        case "$s" in ''|*/*|.*) continue ;; esac
        if ! grep -qxF "$s" "$list.new" && [ -f "$SKILLS_DIR/$s/SKILL.md" ]; then
          rm -rf "${SKILLS_DIR:?}/$s"
          echo "  gone  skill $s (no longer in the repo)"
        fi
      done < "$list"
    fi
    mv "$list.new" "$list"
    echo "  ok    skills -> $SKILLS_DIR"
  fi
  if [ -f "$AGENT_DIR/setup.sh" ]; then
    AGENT_DIR="$AGENT_DIR" PYTHON="$PYTHON" bash "$AGENT_DIR/setup.sh" || { echo "  fail  $name setup.sh" >&2; return 1; }
  fi
  [ "$rules_failed" = 0 ]
}

install_agents() {
  local env
  for env in "$SRC"/agents/*/agent.env; do
    if ! install_agent "$(dirname "$env")"; then
      FAILED_AGENTS="$FAILED_AGENTS $(basename "$(dirname "$env")")"
    fi
  done
}

# A hook that is not ours is kept as <hook>.local and runs first, if it is executable: its
# mode is left as it was, so a hook you had switched off stays off. If <hook>.local is
# already someone else's too, nothing is overwritten and that hook is left alone. A
# symlinked hook is never written through: it may point outside the repo.
# Returns 0 installed, 3 left alone, 1 failed.
is_ours() {  # $1 file: one of our hooks, by the header lines only we write
  local header name
  header="$(head -n 6 "$1" 2>/dev/null)"
  name="$(basename "$1")"
  printf '%s\n' "$header" | grep -qxF "# ai-dotfiles hook: $name" && return 0
  printf '%s\n' "$header" | grep -qE "$TYPED_HOOK" && return 1
  printf '%s\n' "$header" | grep -qE "$LEGACY_HOOK"
}

put_hook() {  # $1 source hook, $2 destination dir
  local dst
  dst="$2/$(basename "$1")"
  if [ -L "$dst" ] || [ -L "$dst.local" ]; then
    echo "  skip  $(basename "$1") in $2: it is a symlink; left alone" >&2
    return 3
  fi
  # A .local that is an exact copy of our hook would only run it twice. One you changed is yours.
  if [ -e "$dst.local" ] && { cmp -s "$dst.local" "$1" || { [ -e "$dst" ] && is_ours "$dst" && cmp -s "$dst.local" "$dst"; }; }; then
    rm -f "$dst.local"
  fi
  if [ -e "$dst" ] && ! is_ours "$dst"; then
    if [ -e "$dst.local" ]; then
      echo "  skip  $(basename "$1") in $2: both it and its .local are someone else's; left alone" >&2
      return 3
    fi
    mv "$dst" "$dst.local" || return 1
    if [ -x "$dst.local" ]; then
      echo "  kept  existing $(basename "$1") as $(basename "$1").local (runs first)"
    else
      echo "  kept  existing $(basename "$1") as $(basename "$1").local (not executable, so it stays off)"
    fi
  fi
  install -m 0755 "$1" "$dst" 2>/dev/null || return 1
}

# pre-applypatch and applypatch-msg only hand off to pre-commit and commit-msg, so those are
# put first, and an am hook whose partner was left alone is not installed either.
am_partner() {  # $1 hook name
  case "$1" in pre-applypatch) echo pre-commit ;; applypatch-msg) echo commit-msg ;; esac
}

# Sets DONE_HOOKS and LEFT_HOOKS. Returns 1, with FAILED_HOOK set, when a hook cannot be written.
put_hooks() {  # $1 destination dir
  local h name partner rc
  DONE_HOOKS="" LEFT_HOOKS="" FAILED_HOOK=""
  while IFS= read -r h; do
    name="$(basename "$h")"
    partner="$(am_partner "$name")"
    if [ -n "$partner" ] && case " $LEFT_HOOKS " in *" $partner "*) ;; *) false ;; esac; then
      echo "  skip  $name in $1: it hands off to $partner, which was left alone"
      # Remove only our old hand-off hook. A hook supplied by someone else still belongs to them.
      if [ -e "$1/$name" ] && [ ! -L "$1/$name" ] && is_ours "$1/$name"; then
        rm -f "$1/$name" || { FAILED_HOOK="$name"; return 1; }
        # The hook we had kept aside as .local would never run again: it goes back in place.
        if [ -e "$1/$name.local" ] && [ ! -L "$1/$name.local" ]; then
          mv "$1/$name.local" "$1/$name" || { FAILED_HOOK="$name"; return 1; }
          echo "  note  restored $name.local in $1 as $name"
        fi
      fi
      continue
    fi
    rc=0
    put_hook "$h" "$1" || rc=$?
    if [ "$rc" = 1 ]; then
      FAILED_HOOK="$name"
      return 1
    fi
    if [ "$rc" = 3 ]; then LEFT_HOOKS="$LEFT_HOOKS $name"; else DONE_HOOKS="$DONE_HOOKS $name"; fi
  done < <(for h in "$SRC"/hooks/git/*; do [ -n "$(am_partner "$(basename "$h")")" ] || printf '%s\n' "$h"; done
           for h in "$SRC"/hooks/git/*; do [ -z "$(am_partner "$(basename "$h")")" ] || printf '%s\n' "$h"; done)
}

git_hooks() {
  local current want norm hooked
  echo
  want="$("$PYTHON" -I -c 'import os, sys; print(os.path.normpath(sys.argv[1]))' "$HOME/.git-templates")"
  current="$(git config --global --get init.templateDir 2>/dev/null || true)"
  norm="$("$PYTHON" -I -c 'import os, sys; print(os.path.normpath(os.path.expanduser(sys.argv[1])) if sys.argv[1] else "")' "$current")"
  # Checked first, so the note is printed whichever template folder ends up in use.
  hooked=""
  if [ -n "$(git config --global --get core.hooksPath 2>/dev/null)" ] || [ -n "${GIT_TEMPLATE_DIR:-}" ]; then
    hooked=1
  fi
  if [ -n "$current" ] && [ "$norm" != "$want" ]; then
    echo "git hooks: init.templateDir is already $current; left as is."
    echo "  note  copy $SRC/hooks/git/* into its hooks/ folder if you want them in new repos"
    [ -z "$hooked" ] || echo "  note  a global core.hooksPath or GIT_TEMPLATE_DIR is set, so git will not use template hooks"
    return 0
  fi
  echo "git hooks -> ~/.git-templates (applies to new inits and clones)"
  # Without git the configured templateDir cannot be read. The hooks still go to ~/.git-templates
  # so a later run only has to set init.templateDir, and the failure below says so.
  if ! command -v git >/dev/null 2>&1; then
    echo "  note  git was not found, so init.templateDir could not be read; if it points elsewhere, these hooks are not used"
  fi
  [ -z "$hooked" ] || echo "  note  a global core.hooksPath or GIT_TEMPLATE_DIR is set, so git will not use these template hooks"
  if [ -L "$want" ]; then
    echo "  fail  $want is a symlink; the template hooks are not written through it" >&2
    return 1
  elif [ -L "$want/hooks" ]; then
    echo "  fail  $want/hooks is a symlink; the template hooks are not written through it" >&2
    return 1
  fi
  mkdir -p "$want/hooks" 2>/dev/null || { echo "  fail  could not create $want/hooks" >&2; return 1; }
  if ! put_hooks "$want/hooks"; then
    echo "  fail  could not write $FAILED_HOOK in $want/hooks" >&2
    return 1
  fi
  if [ -z "$current" ]; then
    if ! command -v git >/dev/null 2>&1; then
      echo "  fail  git was not found, so init.templateDir is not set; run the installer again once git is installed" >&2
      return 1
    elif ! git config --global init.templateDir "$want" 2>/dev/null; then
      echo "  fail  could not set init.templateDir: new repos will not get the hooks" >&2
      return 1
    fi
  fi
  echo "  ok   $DONE_HOOKS"
  if [ -n "$LEFT_HOOKS" ]; then
    echo "  partly installed: left alone$LEFT_HOOKS (see above)" >&2
    return 1
  fi
}

# 0 every hook installed, 3 some left alone, 2 hooks folder is a symlink, 1 failed.
hook_repo() {  # $1 .git folder
  [ -L "$1/hooks" ] && return 2          # a hooks folder that points elsewhere is not ours to fill
  mkdir -p "$1/hooks" 2>/dev/null || return 1
  put_hooks "$1/hooks" || return 1
  [ -n "$LEFT_HOOKS" ] && return 3
  return 0
}

existing_repos() {  # $1 root
  local root="$1" g repo rc
  echo
  if [ ! -d "$root" ]; then
    echo "existing repos: $root is not a folder" >&2
    return 1
  fi
  echo "existing repos under $root"
  # -maxdepth 5 finds a .git up to five levels down, which is a repo up to four levels below DIR.
  local failed=0
  while IFS= read -r -d '' g; do
    repo="${g%/.git}"
    if [ -n "$(git -C "$repo" config --get core.hooksPath 2>/dev/null)" ]; then
      echo "  skip  $repo (uses core.hooksPath; its hook manager owns the hooks)"
      continue
    fi
    rc=0
    hook_repo "$g" || rc=$?
    case "$rc" in
      0) echo "  hooked $repo" ;;
      3) echo "  partly hooked $repo (see the skipped hooks above)" >&2; failed=1 ;;
      2) echo "  skip  $repo (its hooks folder is a symlink)" ;;
      *) echo "  fail  $repo" >&2; failed=1 ;;
    esac
  done < <(find "$root/" -maxdepth 5 -type d -name .git -print0 2>/dev/null)
  [ "$failed" = 0 ]
}

usage() {
  sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

main() {
  local repos="" want_repos=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help) usage; exit 0 ;;
      --existing-repos)
        if [ $# -lt 2 ] || [ -z "$2" ]; then
          echo "--existing-repos needs a folder" >&2; usage >&2; exit 2
        fi
        want_repos=1; repos="$2"; shift 2 ;;
      *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
  done
  if [ "$want_repos" = 1 ] && [ ! -d "$repos" ]; then
    echo "existing repos: $repos is not a folder" >&2
    exit 2
  fi

  echo "source: $SRC"
  PYTHON="$(command -v python3 || true)"
  if [ -z "$PYTHON" ]; then
    echo "python3 is required" >&2
    exit 1
  fi
  export PYTHON
  trap 'rc=$?; cleanup; exit $rc' EXIT
  take_lock

  echo
  echo "shared -> $SHARED"
  rc=0
  install_release || rc=$?
  if [ "$rc" -eq 2 ]; then
    echo "partly installed: fix what is named above (permissions, most often) and run the installer again" >&2
    exit 1
  elif [ "$rc" -ne 0 ]; then
    echo "done, but nothing was installed: the release could not be copied into $SHARED/releases" >&2
    exit 1
  fi
  # From here on a failed step is reported and the rest still runs.
  record_source || FAILED_STEPS="$FAILED_STEPS source-record"
  seed_user_files || FAILED_STEPS="$FAILED_STEPS user-files"
  zsh_trigger || FAILED_STEPS="$FAILED_STEPS zsh-trigger"
  install_agents
  git_hooks || FAILED_STEPS="$FAILED_STEPS git-hooks"
  if [ "$want_repos" = 1 ]; then
    existing_repos "$repos" || FAILED_STEPS="$FAILED_STEPS existing-repos"
  fi
  echo
  if [ -n "$FAILED_AGENTS$FAILED_STEPS" ]; then
    [ -n "$FAILED_AGENTS" ] && echo "done, but these agents were not fully installed:$FAILED_AGENTS" >&2
    [ -n "$FAILED_STEPS" ] && echo "done, but these steps failed:$FAILED_STEPS" >&2
    exit 1
  fi
  echo "done"
}

main "$@"
