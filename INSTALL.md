# Install
<!-- hygiene:ignore-file - contains verification fixtures that quote the scanned patterns -->

Universal rules, enforcement tooling and skills for every AI agent on this
machine.

```bash
./install.sh
./install.sh --existing-repos ~/Documents
```

Idempotent. Edit anything here and re-run. Claude Code, Codex, Cursor and Hermes are
configured only when their folder exists. Gemini CLI, OpenCode and the ChatGPT
reference copy (`~/.chatgpt/`, with the skills) are written either way, so the rules
are in place before the tool is. The Claude app gets no file, only the paste step. If
an agent or a step cannot be completed (a rules file, the git template hooks, `git
config`, a repo under `--existing-repos`), the rest is still installed and the
installer exits 1 naming what failed. The exception is the shared release: when it cannot be
copied or switched over, the installer says so ("nothing was installed" or "partly
installed") and stops before the agents and hooks. Exit 2 is a usage error. `./install.sh --help` prints the usage; an unknown
argument is an error, not an install.

---

## Architecture

One source of truth, four delivery layers, each covering a failure of the one
above it.

```
rules/RULES.md  (source of truth)
    |
    +-- ~/.ai-rules/RULES.md          canonical copy + shared tooling
    +-- ~/.claude/CLAUDE.md           Claude Code reads this
    +-- ~/.codex/AGENTS.md            Codex reads this
    +-- rules/paste-into-chat-ui.txt  for app UIs with no config file
```

| Layer | Mechanism | Scope | Reliability |
|---|---|---|---|
| 1 | Rules files | Per agent | Instruction. Usually followed, not guaranteed |
| 2 | `settings.json` flags | Claude Code | Unreliable, see below |
| 3 | Claude Code hooks | Claude Code | Deterministic within a session |
| 4 | **Git hooks** | **Every tool** | **Deterministic at the git layer** |

Layer 4 is the one that makes this universal. Claude Code, Codex, Cursor, a paste
out of a chat window, a tool installed next year, or a human typing: all of it
reaches git eventually, and new content passes through the same gate: a commit, or a
patch applied with `git am`. Merges, cherry-picks, reverts and rebases carry commits that
were already made, so they are not scanned and keep their messages as they were, except
that a merge or cherry-pick finished with `git commit` (or `git cherry-pick --continue`)
after a conflict runs the message hook like any commit, so attribution trailers are then
removed. `git rebase --continue` does not run it. At an interactive-rebase "edit" stop,
new content committed with `git commit` or `git commit --amend` is scanned, but changes
staged and left for `git rebase --continue` to commit are not: git commits them without
running any hook.

**On layer 2.** `includeCoAuthoredBy: false` is set because it is harmless if it
works, but it has been reported as inconsistently honoured, and a
`Claude-Session:` trailer has been reported as driven server-side.
`attribution: {commit, pr}` is *not* set, because that key is unverified.

---

## What gets installed where

**Shared** (`~/.ai-rules/`)

Each install is a complete copy under `releases/`; `current` points at the newest and
`bin`, `engine`, `rules`, `config`, `skills`, `shell`, `agents` and `RULES.md` are links
into it, so everything switches at once. The newest three releases are kept.

| Path | Role |
|---|---|
| `bin/content-hygiene` | Scanner: hidden text, characters, placeholders, scaffolding |
| `bin/check-deps` | Imports not declared in the project manifest (a language with no manifest at all is not checked) |
| `bin/harness`, `bin/context-manager.py`, `engine/` | The project engine (see `docs/ENGINE.md`) |
| `RULES.md`, `rules/` | The rules, their detail files and the domain rules |
| `harness-exclude`, `trusted` | Yours to edit. `harness-exclude` is created once; `trusted` lists the git repos where the engine may write tracked files, and is written by `harness trust` |

**Claude Code** (`~/.claude/`)

| File | Role |
|---|---|
| `CLAUDE.md` | Rules, generated from `rules/RULES.md`, loaded every session |
| `hooks/pre-write-guard.sh` | PreToolUse on Write, Edit, NotebookEdit: blocks defective writes |
| `hooks/post-write-audit.sh` | PostToolUse: reports unresolved imports |
| `hooks/session-start.py`, `hooks/prompt-route.py` | Project setup, model and task notes |
| `skills/`, `agents/`, `commands/` | All skills, the seven subagents, the seven slash commands |
| `settings.json` | The four hooks and `Read(~/.claude/skills/**)`; merged, your other keys and hooks kept, with numbers and non-ASCII text written as they were. A symlinked file is written through its link and the file's mode is kept (a new one is created private). A file the installer cannot safely rewrite is left untouched, the hooks are then not registered, and the installer says so and exits 1: one that is not valid JSON (comments and trailing commas are not JSON), is read-only, sits in a folder the installer cannot write (the new copy is made beside it), repeats a key within one object (only the last would survive a rewrite), or whose `hooks` or `permissions` have an unexpected shape |

**Codex** (`~/.codex/`) gets `AGENTS.md` and all skills. **Gemini CLI** (`~/.gemini/`)
gets `GEMINI.md` and all skills. **OpenCode** (`~/.config/opencode/`) gets `AGENTS.md`;
it reads skills from `~/.claude/skills/`, so no second copy. Gemini and OpenCode install
even when the tool is not, so the rules are in place on first run.

A rules file you edited by hand is copied to `<file>.bak-<time>` before it is
regenerated. A file the installer wrote itself, and has a record of writing, is
replaced without a backup. The first run of this installer over files from an older
version has no such record, so it backs each of them up once. A symlinked rules file
keeps its link.

**Git** (`~/.git-templates/hooks/`; a symlinked `~/.git-templates` or hooks folder is not written through: the installer says so and exits 1)

| File | Role |
|---|---|
| `commit-msg` | Strips AI attribution trailers |
| `pre-commit` | Blocks hygiene violations in the staged content |
| `pre-applypatch`, `applypatch-msg` | During `git am`, hand each patch to our type-marked `pre-commit` and its message to our type-marked `commit-msg`; they do nothing when the hook beside them has the wrong type, is not ours, or is a symlink |
| `post-checkout`, `post-merge` | Keep a project's setup current; never fail the git command |

A hook of yours with the same name is kept as `<hook>.local` and runs first when it
is executable; its mode is not changed, so a hook you had switched off stays off. If
both the hook and its `.local` are yours, ours is not installed for that hook, and the
repo or the template folder is reported as partly installed, and the installer exits 1.
When `pre-commit` is left alone this way, or because it is a symlink, our
`pre-applypatch` is not installed either, and the same goes for `commit-msg` and
`applypatch-msg`, so `git am` never runs your hook out of turn. If an earlier install
had kept your `pre-applypatch` or `applypatch-msg` as `.local`, removing ours puts
yours back under its own name, and the installer says so. A `.local` that is an
exact copy of our hook is removed, since it would only run twice; one you changed is
kept. A hook that is a symlink is left alone. Our own
hooks are replaced on every install, so put changes in `<hook>.local`, not in the
hook. If `init.templateDir` already points somewhere else, it is left alone and no
template hooks are installed. Without git, `init.templateDir` cannot be read: the hooks
are still written to `~/.git-templates`, the installer says the setting was not read,
and the step fails until git is installed.

A skill folder is replaced whole on install, so do not keep notes inside one. A skill
the repo no longer has is removed; a skill of your own under another name is kept. The
seven subagents and slash commands are overwritten by name.

`AI_RULES_HOME` moves the shared folder away from `~/.ai-rules`. The hooks look it up
when they run, so it has to be set in the environment of your shell and your tools as
well, not only for the install; otherwise they look in `~/.ai-rules` and do nothing.

**zsh** (`~/.zshrc`, or `$ZDOTDIR/.zshrc` when `ZDOTDIR` is exported): one marked block
that sources `~/.ai-rules/shell/harness.zsh`. If you set `ZDOTDIR` in `~/.zshenv`
without exporting it, the installer cannot see it; move the block to the right file.

OpenCode limit: a project-level `AGENTS.md` takes priority, and the global file
is not loaded in that project. Codex limit: global plus project `AGENTS.md`
share a 32 KiB cap, and the global file uses about 7 KiB.

Cursor and Windsurf keep global rules in their app settings rather than a file.
`agents/cursor/` prints the paste step when Cursor is installed; Windsurf has no
agent folder: paste `rules/paste-into-chat-ui.txt` there, or rely on a
project-level `AGENTS.md`. See `README.md` for adding an agent.

---

## Verify

```bash
~/.ai-rules/bin/content-hygiene --self-test      # last line: N/N passed
~/.ai-rules/bin/content-hygiene FILE...         # exit 0 clean, 1 blocked, 3 a file missing or unreadable
```

Claude Code: `/memory` lists `~/.claude/CLAUDE.md`, `/skills` lists
`ai-content-forensics`. Restart the app first so the new `settings.json` loads.

Codex: `head ~/.codex/AGENTS.md` shows the rules.

Write hook:

```bash
printf '{"tool_name":"Write","tool_input":{"file_path":"/tmp/t.py","content":"# TODO: implement logic\\n"}}' \
  | ~/.claude/hooks/pre-write-guard.sh
```

Expect the findings and exit code 2.

Git layer, the important one:

```bash
cd /tmp && rm -rf ht && mkdir ht && cd ht && git init -q
git config user.email t@example.com && git config user.name Test
printf 'const m = \xe2\x80\x9chi\xe2\x80\x9d;\n' > app.js && git add app.js
git commit -m "test"
```

Expect the commit to be blocked with a curly-quote finding.

---

## App UIs with no config file

ChatGPT and Claude chat take rules through account settings, not a file, so
`agents/chatgpt-app/` and `agents/claude-app/` print the step on every install.
The ChatGPT entry also keeps a reference copy in `~/.chatgpt/`, which the app does not read.
The setting is per account: once saved, it applies to the desktop app, web and
mobile. Copy the text with:

```bash
sed -n '3,$p' rules/paste-into-chat-ui.txt | pbcopy
```

About 1,320 characters, which fits the smallest known limits:

- **ChatGPT** - Settings, Personalization, Custom instructions, the "how should
  ChatGPT respond" box. 1,500 characters on Free and Go, 5,000 on paid plans
  (reported July 2026).
- **Claude** - Settings, the personal preferences field. Guides report a 1,500
  character limit; not confirmed on Anthropic's own pages.

The Claude app's Code tab is Claude Code and is already covered by
`agents/claude-code/`.

This is instruction only. There is no enforcement layer inside a chat app; what
you paste out of one still meets the git hooks.

---

## Hook behaviour

Both hooks use one scanner, `bin/content-hygiene`. It sorts a file into code, prose
(`.md`, `.mdx`, `.txt`, `.rst`, `.adoc`, `.org`, `.tex`, and `LICENSE`, `README`,
`CHANGELOG` and the like without an extension) or data (`.json`, `.yaml`, `.csv`,
`.html`, `.xml`, `.po`, `.ipynb` notebooks and similar). Manifests and CI workflows count as code whatever
their extension (`package.json`, `*requirements*.txt`, `requirements/*.txt`, `constraints*.txt`,
`pyproject.toml`, `setup.cfg`, `pom.xml`, `environment.yml`, `pnpm-workspace.yaml`, `renovate.json`,
Compose files and their overrides, `.github/workflows/*`, `.gitlab-ci.yml` and `.gitlab/**/*.yml`,
`.travis.yml`). In GitHub Actions, free text stays text in flow maps with bare, single-quoted or
double-quoted keys, flow sequences and block scalars, including `env:`/`variables:` maps and
concurrency. `${{ }}` expressions
are always judged exactly, including expressions with quoted braces. A `with:` input for a
repository, ref or path, any input with `version` in its name, and an input named
`url`, `uri`, `host`, `hostname`, `endpoint`, `server` or `registry` must be exactly
what it looks like. The same applies to keys ending in `-url`, `_url`, `-uri`, `_uri`,
`-host`, `_host`, `-endpoint`, `_endpoint`, `-server`, `_server`, `-registry` or
`_registry`, and to values that look like a URL or host.

Blocked in every kind of file:

- hidden text: Unicode tag characters (invisible ASCII a model still reads; the
  England, Scotland and Wales flags are the only exception), variation selectors where
  none belongs (after plain text, a letter, box drawing or a symbol with no emoji form),
  runs of eight or more private-use characters, blank lookalikes such as
  the Hangul filler or the braille blank, zero-width characters outside the scripts
  that use them, word joiner, unassigned code points that show as nothing, and any
  other invisible format character (a soft hyphen inside a word is the exception: a
  warning in prose and data, where it marks a hyphenation point)
- control characters: escape sequences, a carriage return inside a line, backspace, NUL
  (a file whose only line breaks are carriage returns is read as old Mac text in prose,
  data and Python; in other code each lone carriage return is a finding)
- an invisible character written as an escape or a character reference (`\U000E0041`,
  `\u200b`, `&#xE0041;`) in code and data; a warning in prose. The escape is judged
  without its neighbours, so it blocks even where the raw character would be allowed: a
  Persian joiner, an emoji sequence or a heart with its selector, as `json.dumps` writes
  them (`\u200c`, `\u200d`, `\ufe0f`), or `&shy;` and `&rlm;` in HTML. Code whose job is to
  strip such characters (a BOM or zero-width remover), and data written that way, need the
  opt-out marker
- unfilled placeholders and code elided with a "rest of the implementation" comment
- generation scaffolding: model self-reference, leaked tool tags or citations

Blocked in code and data, a warning in prose: bidirectional controls.

Blocked in code, a warning in prose and data, where they can be content:

- spaces that are not the plain space, full-width, circled and mathematical styled
  letters
- lookalike words: Latin mixed with Cyrillic, Greek, Armenian or Cherokee letters that
  read as Latin. A word of up to four letters that mixes Latin with the small Greek
  alpha, gamma, kappa, rho (or the rho symbol), sigma or upsilon (rho plus `max`, common
  in numeric code) is a warning, except in a manifest or workflow, where it is blocked.
  Nu, iota and omicron with a suffix are always blocked (nu plus `min` reads as `vmin`).
  In code, a name made only of such letters, or a single one standing
  alone (a Cyrillic `о` as a variable), is blocked unless a real word of each of its
  scripts is in the code within three lines; a whole word of them inside a
  string or a short comment is a warning, and a single letter there is not reported.
  A name that Python and other tools read as a different plain-ASCII name (a script
  `ℯ`, a ligature, full-width letters) is blocked in code, outside strings and
  comments. Superscripts, subscripts and circled numbers (`m²`, `H₂O`) cannot be part
  of a name and are not reported. Also blocked in code: a name that reads as another
  name in the same file (`user_а` beside `user_a`; one Greek letter with an index, `ρ0`
  beside `p0`, is exempt), and a digit of another script
  inside a name with no letter of that script (a Bengali `০` in `t০ken`). In prose and data, words made only of another script's letters are
  that language and are not reported.
  A host name (after `://`, after `user@`, or a bare dotted name whose last label is 2-24
  ASCII letters and is not a common file extension, when no `(` or method chain follows)
  with such a word in it is blocked everywhere, in
  prose, strings, comments and shell arguments too, unless a good share of the letters of
  that label, judged on its own, are real letters of one script (a Russian domain). In code
  outside strings and comments, only `://` and the dotted `user@host` shape mark a host.
  Compact or spaced matrix expressions (`W@x`, `A @ B`) and line-start decorators do not.
  Julia, Lean, Agda, Haskell and Idris keep mathematical letter styles distinct, so
  their conventional mathematical names are not folded to ASCII (monospace and
  sans-serif letters, which look like ASCII, are still blocked, and so is a multi-letter
  name that reads as another name in the file).
- a pair of curly quotes used as string delimiters (`x = “hi”`, `print(“hi”)`: the
  opening one right after `=`, `(`, `,`, `:`, `[`, `{` or `return`, its partner right
  before `)`, `]`, `,`, `;`, `}`, a line comment or the end of the line, with letters or digits
  between), and a non-breaking or other odd space where code needs a plain one (in a
  language the scanner parses; in a manifest or a file type it does not, a warning). In files
  that mix code and a page (JSX, TSX, a `.js` file with JSX tags in it, Vue, Svelte,
  Astro, PHP, ERB, EJS, Handlebars, Jinja, Twig) only the code counts: `<script>` and `<style>` blocks, Astro frontmatter,
  PHP and template-language code blocks, and JSX outside the text between
  tags. The page text around them is prose. These break the program. Strings and
  comments are found across lines (docstrings, block comments, template literals,
  heredocs) for the common languages; in a language the scanner does not know, these
  are a warning, since it cannot tell text from code there

Curly quotes, dashes and the ellipsis anywhere else in code (a string, a comment, JSX
text, a heredoc, a regex class like `/[“”]/`) are a warning, not a block: they are text there, and a stray one in
real code is a syntax error the compiler reports. The middle dot is a warning
everywhere. A math sign that looks like an operator (`−`, `×`, `÷`, `→`, `≤`, `≠`)
in code outside strings and comments is a warning too.
- eight or more private-use characters spread through a file are blocked in prose and
  data and a warning in code, where terminal and editor configs use icon fonts

In prose only: a template slot such as `[Name]` or `[Company]` is blocked, other
bracketed words (`[Unreleased]`, `[Enter]`) are a warning, and a chat opener or closer
("Certainly!", "I hope this helps") is blocked on the first or last lines of a file
and a warning elsewhere. Text that a rendered page hides (an HTML comment on one line
or many, an element styled out of sight, a link title) is a warning when it reads
like an instruction to a model.

Characters that a writing system needs are allowed where they belong: joiners inside
emoji sequences and in Arabic, Persian and Indic text, direction marks in right-to-left
text, the zero-width space between Thai, Lao, Khmer and Myanmar words, the ideographic
space and full-width letters in CJK text, a byte order mark at the start of a file
(a warning), Greek letters such as delta or lambda in code.

A file with a text extension is always scanned: NUL bytes and invalid UTF-8 are
reported, not treated as a reason to skip it, and UTF-16 with a byte order mark is
decoded.

**`pre-write-guard.sh`** covers Claude Code's file tools only: a file written through the
Bash tool (`sed -i`, a redirect, a heredoc) is not seen by it, and only the git hooks
catch that. It runs the scanner on `Write`, `Edit`, `NotebookEdit` and
multi-edit content before it reaches disk (the first 2 MB), and blocks on a hard
finding. It gives the scanner the full path, so a workflow file is judged as code. An
edit is judged where it lands: the file on disk is scanned before and after the edit is
applied, and a finding counts when it is on a line the edit changed or was not in the
file before. So text inside a docstring stays text, new code that closes a string is
seen as code, an edit (or a deletion) that turns old text into code is charged with
what that exposes, and an old finding elsewhere in the file is not charged to the edit.
When the file after the edit has more hard findings than the scanner lists (200), the
guard rescans from the first changed line to the end (from line 1 when the edit deletes
the first line), so old findings cannot hide a finding
the edit exposes farther down. A file-wide count (private-use characters, selectors, joiners) the file
already had is not charged to an edit unless the count grows, the edit brings in such a
character, or those characters no longer read in their old order with at most some left out
(lines that trade places are charged). The guard counts private-use characters and selectors
itself too, so an edit that adds to them is charged even where the scanner leaves out the
file-wide row. Old text is matched the way Claude Code matches it (as written, then with curly
quotes made straight, then with `\uXXXX` escapes read as characters or written as them), and the
new text is given the quote style or escapes Claude Code gives it, so the guard scans what lands
on disk. An edit that cannot be placed is judged on its own, without the first-line and
last-line rules. A multi-edit with an edit Claude Code refuses (its old text is not in the
file even so, or is there more than once without `replace_all`) is judged on its new text alone:
nothing is written, so a block costs nothing. The file is read the way Claude Code reads it
(UTF-16 by its byte order mark, invalid UTF-8 bytes replaced, CRLF line ends matched as LF). An
edit to a file larger than the scanner reads (2 MB as UTF-8) is judged on its new text alone when
it only adds text (each old text kept whole in its new text), and is otherwise a block
("not-checked"). A
relative path is read from the hook input's `cwd`, or else the folder the hook started in. A notebook cell edit that gives no cell type takes the type of the
cell it replaces; a cell that cannot be found is judged as code. It needs only `bash` and `python3`. The opt-out marker counts when it is in
the file: in the text of a whole-file write, or in the first 30 lines of the file on
disk and remains in the first 30 lines after an edit. A marker added by an edit does not excuse that edit. When an edit cannot be placed in time the marker does not excuse it; when it cannot be placed at all, the marker excuses it only if no old text reaches into the marker and the marker stays in the first 30 lines.

**`pre-commit`** applies the same hard checks to the content being committed (the
staged bytes of each file, not the copy on disk and with no encoding conversion) and
blocks the commit. It judges
each added or changed file as a whole, not only the changed lines; a file that was
only moved is not judged again, unless the move changes how it is judged (a new
  extension, a name that makes it a manifest such as `requirements.txt`, or a move into
  `.github/workflows/`). It also prints the hidden-text warnings (bidirectional
controls, lookalikes, hidden instructions) without blocking. Bypass with
`AI_HYGIENE_SKIP=1 git commit` or `--no-verify`.

**`commit-msg`** removes, in any letter case: a `Co-authored-by`, `Co-developed-by`,
`Assisted-by`, `Generated-by`, `Signed-off-by` or `Reviewed-by` trailer that carries an
AI tool's own address; a `Co-authored-by`, `Co-developed-by`, `Signed-off-by`, `Assisted-by` or `Generated-by`
trailer naming a tool nobody is called (Copilot, Codex, ChatGPT, Claude Code, Claude
Opus and so on) with any address, or `Claude` with no address;
`Claude-Session:` and session links; and "Generated with [tool]" or "Created with
tool" lines that end at the tool's name. A message made only of such a line ends up empty, and git
then stops the commit; write a real message. `Co-authored-by: Claude <claude@example.fr>`
is taken to be a person and kept, and so is a sentence that mentions a tool.

### Where each layer lets things through

These are guardrails. Each one fails open when the tool it needs is missing, rather than stop your work; once it runs, a failure part way through blocks.

| Layer | Lets a write or commit through when |
|---|---|
| Scanner | the file has a binary extension (`.png`, `.pdf`, `.zip` and the like); the content is past the first 2 MB; more than a tenth of a file with no text extension is NUL or undecodable bytes; the hidden text uses a lookalike or trick it does not know, or is spread out under its thresholds: fewer than 16 variation selectors or Hangul fillers in a file, each in a place where one can belong, fewer than 8 private-use characters (in code, where icon-font glyphs are common, the file-wide count is a warning and only a run of them blocks), one presentation selector per emoji, or joiners and direction marks at a density real Persian, Arabic or Hebrew text could have. It checks characters and a few fixed phrases (read in the first 2,000 characters of each line) and does not judge what visible text says |
| Write guard | the scanner or `python3` is missing; the hook input is not readable JSON or the content is not text. A scanner or a guard that fails part way is a block ("not-checked"), not a pass. An edit is scanned twice, side by side (the file before and after the edit). A file of 100000 characters or more is scanned whole without the 200-finding cap when the scanner takes `--no-cap`; otherwise, only when the new file is over the cap, once more from the first changed line. Each scan has the time left of the guard's 12 seconds. Placing the edit in the file (or building a new file from a multi-edit) runs in a child process the guard can stop, until 5 seconds before the 12 run out; an edit that cannot be placed in time, or a child that cannot be started, is a block ("not-checked"). An edit that does not match the file, or a multi-edit that Claude Code refuses, is judged on its new text alone. The guard as a whole stops 12 seconds after its bash started, inside the hook's 15-second limit; a scan or a guard that has not finished in time is a block ("not-checked"), not a pass. It shows blocks only, never warnings |
| pre-commit | `python3` is missing or the staged files cannot be copied for scanning (it says so; `AI_HYGIENE_STRICT=1` blocks instead); the commit is a merge, cherry-pick, revert or rebase (it carries commits already made; a patch applied with `git am` is scanned); changes staged at an interactive-rebase "edit" stop are committed by `git rebase --continue` (only `git commit` or `git commit --amend` at the stop is scanned). A staged file whose name cannot be created on this disk (a name that is not valid UTF-8 on APFS, say) blocks the commit as "not-checked", since it cannot be copied out to scan; `AI_HYGIENE_SKIP=1` lets it through. A file the scanner has not finished within 60 seconds of its batch (files are scanned 200 at a time) blocks the commit as "not-checked" (bypass with `AI_HYGIENE_SKIP=1` if you know the file); the scan never runs open-ended; the scanner is missing, not executable or cannot start (it says so on stderr every time; `AI_HYGIENE_STRICT=1` blocks instead). A file that makes the scanner fail part way is reported as "not-checked" and blocks, so no content can switch the check off; `AI_HYGIENE_SKIP=1` or `--no-verify` is used. Warnings never block |
| commit-msg | the attribution is worded in a way the patterns above do not cover; the commit is a merge, cherry-pick, revert or rebase, where git keeps the message as it was (unless a merge or cherry-pick conflict is finished with `git commit` or `git cherry-pick --continue`, which runs it) |

**`post-write-audit.sh`** and the pre-commit dependency pass never block, and stop
after about 9 seconds whatever they are doing (in pre-commit, per batch of 200 files). Manifests
that are symlinks are not read, and at most 20 `requirements*.txt` files per project.
The standard library, packaging tools (`pip`, `setuptools`), Node built-ins (anything
under `node:`) and the project's own modules are not reported. They
report imports absent from `package.json`, `requirements*.txt` or
`pyproject.toml`, reading the files on disk. False positives are expected for monorepo aliases and
transitive imports.

**Opting out.** A file that must legitimately contain scanned characters carries
`hygiene:ignore-file` in its first 30 lines. The rules files and the forensics
references use it. In the write hook only, these are also exempt: the forensics
references named `skills/ai-content-forensics/reference/forensics-*` (other files in that
folder are checked), the hygiene tooling's own
files (`content-hygiene`, `pre-write-guard.sh`, `post-write-audit.sh`, matched by file
name only where they are installed), and anything under a `.trash-preview/` folder. These
exemptions apply only inside the resolved shared folder or `~/.claude/hooks`; similarly named
sibling folders are checked. A path containing `..` gets no exemption.

---

## Limitations

- **`--no-verify` bypasses it.** A guardrail, not a security control.
- **Server-side commits skip it.** Cloud agents never touch a local hook.
- **PR bodies are not covered.** Commit messages only. CI backstop:

```yaml
- name: Block AI attribution
  run: |
    if git log origin/main..HEAD --format=%B | grep -qiE \
      'Co-Authored-By:.*(Claude|Anthropic|Copilot)|Claude-Session:|Generated with \[Claude'; then
      echo "::error::AI attribution found in commit messages"; exit 1
    fi
```

- **History is not rewritten.** Existing commits keep their trailers.
- **New repos only, unless you bulk-apply.** `init.templateDir` covers repos you
  init or clone from now on; `--existing-repos DIR` adds them to repos up to four
  levels below DIR, skipping any that set `core.hooksPath` (husky and similar) or
  whose hooks folder is a symlink.

---

## What this does not do

It does not affect the statistical text watermark, which has no opt-out. That is
also not what these layers target: the watermark lives in free word choices, so
code carries almost none of it, and models released before 2 August 2026 carry
none at all. What is controllable is attribution metadata and output quality.

A Unicode-stripping tool does not remove a watermark. It removes copy-paste
artifacts, which are a different thing.

---

## Maintenance

- Keep `rules/RULES.md` short. It is in context on every turn in every agent.
- When a rule is violated, rewrite that rule rather than adding another.
- Re-run `./install.sh` after any edit, and after installing a new agent.
- Re-verify volatile claims. Watermark coverage is per model version and goes
  stale on its own.

## Harness layer: agents, commands, config, bootstrap

What `install.sh` now installs beyond rules and skills:

- Subagents (`agents/definitions/*.md`): copied to `~/.claude/agents/` by the claude-code setup. Seven agents: planner, code-reviewer, security-reviewer, tester, architect, performance-optimizer, documentation-guide.
- Slash commands (`commands/*.md`): copied to `~/.claude/commands/`. Seven commands: `/plan`, `/review`, `/test`, `/security`, `/architecture`, `/optimize`, `/docs`.
- Shared copies under `~/.ai-rules/`: `rules/` (domain rules), `skills/`, `agents/definitions/`, `config/` (budgets, relevance, skill metadata), and `bin/` (only `check-deps`, `content-hygiene`, `context-manager.py` and `harness`; any other file in the repo's `bin/` is not installed).
- Vendors: Cursor (paste step for user rules; project rules are `.cursor/rules/*.mdc` per repo), Hermes (skills to `~/.hermes/skills/`), Devin (reads `AGENTS.md` per repo; no local install).

Vendor coverage is limited to what each tool supports. Slash commands and subagents are installed for Claude Code only.

### Per project: automatic

`install.sh` also installs the project engine, a SessionStart hook, a `cd` trigger block in `~/.zshrc`, and `post-checkout` and `post-merge` git template hooks. Projects are then set up and kept current without any command. A git repo is set up without touching any tracked file until you run `harness trust` in it. Exclusions go in `~/.ai-rules/harness-exclude`, trusted repos in `~/.ai-rules/trusted`. Everything the engine does, and how to switch it off: `docs/ENGINE.md`.

```bash
~/.ai-rules/bin/harness status
~/.ai-rules/bin/harness doctor
~/.ai-rules/bin/harness trust
```

The prompt hook's model note and task note go through the decision engine. Turn both off with `touch ~/.ai-rules/router.off`; `touch ~/.ai-rules/harness.off` turns the whole engine off. How the base and project layers combine: `docs/CASCADE.md`.

### Self-test

```bash
python3 ~/.ai-rules/bin/context-manager.py --self-test
test -x ~/.claude/hooks/prompt-route.py && python3 ~/.claude/hooks/prompt-route.py --self-test
python3 -m unittest discover -s tests
```

Config files are JSON rather than YAML so the tools run without PyYAML.
