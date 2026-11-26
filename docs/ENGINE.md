# Project engine

The engine sets up every project on this machine by itself and keeps that setup current as the project changes. It logs its own changes, points agents at where decisions are recorded, and keeps what loads into every session under a checked token cap.

Code: `engine/`, the `bin/harness` CLI, and `config/`. Installed under `~/.ai-rules/`.

## When it runs

Nothing needs to be run by hand. Each trigger calls the same entry point, which returns in milliseconds when nothing changed.

| Trigger | Fires | Installed as |
|---|---|---|
| Claude Code session start | opening or resuming a session | SessionStart hook |
| Claude Code prompt | every prompt, including short ones and slash commands | UserPromptSubmit hook |
| `cd` in zsh | entering a folder in a terminal, for Codex, Gemini, OpenCode and anything else | a marked block in `~/.zshrc` |
| git `post-checkout`, `post-merge` | after a clone, a checkout or a pull, in repos created or cloned after install, and in repos hooked with `--existing-repos` | `~/.git-templates` |

`harness init` forces a setup the engine declined or that you removed. `harness trust` moves a git repo of yours from local to full mode.

## What counts as a project

The root is found in this order:

1. the git root, unless it is a container (below);
2. else the highest folder with a manifest, below the nearest container. A folder of packages inside a manifest project (`mono/packages/`) belongs to that project, so a monorepo without git is one project;
3. else a workspace: a folder with no marker of its own that wraps exactly one project (for example `tracker/{design,repo,research}`). Stack and commands are read from the inner project and commands are prefixed with `cd <name> &&`. The inner folder must have a plain name (letters, digits, `.`, `_`, `-`);
4. else the folder directly below the nearest container or home.

Manifests cover Node, Deno, Python (`pyproject.toml`, `requirements.txt`, `setup.py`, `setup.cfg`, `Pipfile`), Rust, Go, Java, Kotlin, Scala, Ruby, PHP, Swift, Dart and Flutter, Elixir, .NET (`*.csproj`, `*.fsproj`, `*.sln`), CMake and Docker files.

Never set up:

- anything outside the home folder, the home folder itself, and `~/Library`
- hidden folders
- containers: the standard folders under home (`Documents`, `Desktop`, `Downloads`, `Developer`, `Projects`, `code` and similar, any letter case), any folder holding two or more git repos, any folder with no marker of its own that holds two or more projects up to two levels down, and any folder with no marker and more than 4,000 entries. A rule file there would load into every project below it. A folder the engine set up earlier that later becomes a container (a second repo is cloned into a workspace, say) is retired: the engine's blocks are removed, your own text stays, and the changelog says so
- dependency and build folders inside a project (`node_modules`, `vendor`, `venv`, `dist`, `build`, `target`) and anything below them, including a package there that has its own manifest
- anything listed in `~/.ai-rules/harness-exclude` (one path or glob per line). The installer lists the ai-dotfiles repo itself; add your own lines. `harness init` refuses such a project too, whether or not it also has a `.harness-skip` file
- a folder whose path contains a control character
- any project with a `.harness-skip` file. In an untrusted repo where that file is committed, `harness init` leaves it in place, because local mode never deletes or writes a tracked file, and records the override in the engine's state on this machine instead; `harness remove` drops the override

A folder with no git and no manifest is decided by the `is_project` question. With a Claude Code session open there, three source files are enough, or one source file plus a `src`, `app` or `lib` folder. From a `cd` alone it takes four files, or two plus such a folder; three files from a `cd` is unsure, so it is asked again at the next session or prompt. An empty folder is not a project until code appears. A folder the engine was unsure about is asked again when its contents change, or at a Claude Code prompt an hour later.

## Two modes

The engine edits tracked files only in a repository you have said is yours.

| | full | local |
|---|---|---|
| Used for | a folder without git, or a git repo on your trust list | every other git repo |
| Block goes to | `AGENTS.md` | `.harness/AGENTS.md` |
| Claude Code loads it through | `@AGENTS.md` in `CLAUDE.md` | `@.harness/AGENTS.md` in `CLAUDE.local.md` (plus `@AGENTS.md` when the repo has an `AGENTS.md` but no `CLAUDE.md`, because a `CLAUDE.local.md` stops Claude Code reading `AGENTS.md` on its own) |
| Hidden from git | no | yes: `.harness/`, `CLAUDE.local.md` and `.harness-skip` are listed in the repo's `info/exclude`, including for worktrees |
| fieldbook | set up once git exists | never run |
| Decisions recorded in | `.fieldbook/bank/04-decisions.md`, or `.harness/decisions.md` until fieldbook exists | `.harness/decisions.md` |

### Trust

Nothing inside a repository can prove whose it is. Commit authors are text that anyone can write, so a cloned repo whose every commit carries your email looks the same as one you wrote. The engine does not guess. A git repo is trusted in one of two ways:

- You run `harness trust` in it (`harness untrust` reverses it). Trusted folders are listed one per line in `~/.ai-rules/trusted`, which you can also edit by hand.
- The engine saw the folder empty and then set it up before it had git. Only a folder made on this machine is ever seen empty: `mkdir app && cd app`, or a Claude Code session opened in a new folder. Empty means nothing in it at all, dotfiles and `AGENTS.md` included; only a Finder `.DS_Store` is ignored. When you later run `git init` there, it is added to the list by itself, as long as the `.git` folder holds only what `git init` and your own commits create: default config, no remote, nothing fetched, pulled or packed, no redirect to another folder (`commondir`, worktrees, alternates), a record in the reflog for every commit, and no hooks other than git's samples and the ones in your `~/.git-templates`. A `.git` that was pulled into, or unpacked or copied in with any of those traces, is not trusted. One that was crafted to look exactly like a fresh `git init` cannot be told apart from the real thing by its files: if you unpack an archive into a folder the engine has already set up, and that archive carries a `.git`, delete it before you work there, or run `harness untrust` afterwards. The engine proves it is the same folder with a random token it wrote to `.harness/.born` at that first setup.

A folder that arrives with files in it (an unpacked download, a scaffolding tool's output) is never trusted this way, whoever runs `git init` in it. The check is on the folder, not on where its files came from: if you make an empty folder, enter it, unpack an archive into it and then run `git init`, that is your folder and it is trusted. Neither is a clone into a folder the engine saw empty, nor a folder where `git init` ran before the first file. In those, run `harness trust` once.

Each line `harness trust` writes carries the folder's identity (device, inode and, on macOS, creation time) after the path, so a different folder that later takes the same path is not trusted. On a Linux disk that gives a deleted folder's inode number to a new one at once, a folder deleted and made again at the same path can be taken for the old one; there is no creation time to tell them apart. The other side of this: a trusted repo you move or rename is no longer trusted at its new path, and drops to local mode (or to skipped, if the engine's files are committed) until you run `harness trust` there. A line you write by hand has no identity and matches by path alone. Trust covers the whole repository: a project in a subfolder of a trusted repo is trusted with it, and a project inside an untrusted repo is in local mode even when it has its own manifest and the repo root is not itself a project.

`harness status` shows the mode and says how to change it. `harness init` does not grant trust. A worktree of a trusted repo is trusted with it. Paths are compared in the letter case they have on disk, so `~/documents/repo` and `~/Documents/Repo` are one project on a case-insensitive disk.

In local mode other tools (Codex, Gemini, OpenCode) do not see the block, because they read `AGENTS.md`. That is the cost of leaving a repository untouched, and `harness trust` is the way out for your own repos.

If git already tracks `.harness/` or `CLAUDE.local.md` under any spelling the disk may treat as the same name (a committed `.HARNESS/AGENTS.md` counts, and so does a long s in place of an s; the engine folds each tracked path itself, since git's case-insensitive matching folds only ASCII letters) in an untrusted repo, the exclude file cannot be written, or the repo's own ignore rules un-ignore any file the engine would write there, the engine skips the project rather than change or show anything. The same holds for an entry whose name a case-insensitive disk treats as `.harness` or `CLAUDE.local.md` (`.HARNESS`, `claude.LOCAL.md`, a long s in place of an s), since git matches names exactly and would neither see it as tracked nor hide it. When the ignore rules change after setup (a pull that brings `!CLAUDE.local.md`), the engine deletes the files it generated there (the changelog only while every line in it is the engine's), keeps files you edited or wrote, and keeps its `info/exclude` block while anything of yours is left for it to hide. When git cannot say whether those files are ignored (a timeout or an error), the engine skips that run and deletes nothing. Whenever it skips or stops early, it first takes out of `CLAUDE.local.md` each import line it added whose file no longer passes the check below (an `AGENTS.md` that a pull gave an `@`, a `.harness/AGENTS.md` that git now tracks), unless git tracks `CLAUDE.local.md` itself. Its lines in `info/exclude` sit in a marked block and only that block is removed later; the same lines written by you stay. A `.git` file (worktree or submodule) is followed only when the folder it names points back at this checkout and neither that folder nor the repository's common folder lies inside the checkout, where the checkout's own index could track its `info/exclude`. A worktree's common folder must also be a real git folder with `HEAD`, `objects/` and `refs/`: one named `.git`, or a bare repository that does not contain the checkout, so a crafted `commondir` cannot make the engine write `info/exclude` into an ordinary folder such as `~/Downloads`. Otherwise the project is skipped. On `harness untrust`, untracked full-mode files are removed, and a tracked `AGENTS.md` or `CLAUDE.md` that still holds the block is left alone and reported in the changelog. If you committed `.harness/` while the repo was trusted, local mode would have to change that tracked folder, so the engine instead stops without touching anything: committed files stay as committed, and untracked engine files stay where they are for you to delete or commit, stops updating it, and `harness untrust` and `harness status` report it as skipped. On `harness trust`, the local files and the `info/exclude` lines are removed.

## What it writes

| Path (full mode) | Content | Owner |
|---|---|---|
| `AGENTS.md`, between `<!-- BEGIN ai-dotfiles:harness -->` and `<!-- END ai-dotfiles:harness -->` | stack, the project's own commands, do's and don'ts for the stack, pointers to domain rules and to where decisions are recorded. Per-stack lines are dropped and the command list shortened to fit 600 tokens | engine |
| `CLAUDE.md`, `@AGENTS.md` between `ai-dotfiles:import` markers | makes Claude Code load `AGENTS.md`. Not added when `CLAUDE.md` already has an `@AGENTS.md` line or is a symlink, and not re-added after you remove it | engine |
| `.harness/CHANGELOG.md` | one line per setup, and one per update that changed something | engine, append only |
| `.harness/decisions.md` | decisions recorded while fieldbook is not set up. In an untrusted repo or a download, the block names it only when the engine created it | you and agents |
| `.harness/.born` | a random token, written only when the folder had no git at first setup; used once to trust the folder when git appears | engine |
| `.fieldbook/` | bank, one log per task, decision records, pruning | fieldbook |
| `.harness/config.json` (optional) | `tier`, `exclude`, `pin` for the loader | you |

Text outside the markers is never changed. Once fieldbook is set up, every line you added to `.harness/decisions.md` is moved into `.fieldbook/bank/04-decisions.md`. That bank counts only in a full-mode git repo or a folder the engine saw empty; one that came inside a download is ignored.

Commands are listed only when the project's files define them: `package.json` scripts (run with the package manager the lockfile or `packageManager` field names), Deno tasks, Composer scripts, Makefile targets, and the standard test and build commands for Python tools the project declares, Cargo, Go, Maven, Gradle, sbt, .NET, Swift, Dart, Flutter, Mix and RSpec.

The do's and don'ts come from `config/project-rules.json`: a universal set plus lines per detected stack.

### Staying out

- Delete the generated block from a file and the engine treats that as a no for this project. It stays out until `harness init`. This is remembered on this machine for this folder; a copy or a restore of the folder is a new folder to the engine. For an opt-out that travels with the project, use `harness remove`, which leaves a `.harness-skip` file.
- In a trusted repo where the engine's files are committed on one branch only, switching to a branch without them makes the engine write them again, untracked. Git then refuses to switch back until you remove or commit them ("untracked working tree files would be overwritten"). Merge the engine's files into the other branch, or delete the untracked copies before switching.
- A missing file, or a file that git replaced with a version lacking the block (a branch switch or a pull, including one that brings other people's commits to the file), is regenerated. A removal you committed yourself in this checkout is respected.
- If a block's markers are damaged, or the file is not valid UTF-8, the file is left untouched until you repair it.
- `harness remove` writes `.harness-skip` first, then deletes the engine's blocks and its changelog. It keeps your decisions, `.harness/config.json` and everything fieldbook owns. A file that held nothing but the engine's block is deleted, which in a trusted repo shows up in git as a deletion for you to commit; `.harness-skip` shows as a new file. In an untrusted repo `.harness-skip` is hidden by `info/exclude`; where the repo's own ignore rules would still show it, the file is not written and the opt-out is kept in the engine's state instead, which `harness init` clears. In an untrusted repo it touches only the local-mode files (`.harness/`, `CLAUDE.local.md`), never `AGENTS.md` or `CLAUDE.md`, and leaves any file git tracks as committed, listing it in its output. The tracked check folds letter case the way the disk does, so a committed `.HARNESS/CHANGELOG.md` or `claude.LOCAL.md` counts as the file it would change. A committed `.harness-skip`, under any spelling, is never written over: the opt-out goes into the engine's state.

### fieldbook

fieldbook writes tracked files and git hooks and runs git itself, so the engine runs it only where all of these hold:

- the repo is in full mode (trusted, or born on this machine);
- the trigger is session start, `cd` or a manual command, never the 10-second prompt hook or the hook that fires right after a clone;
- `.git` is a plain folder (not a worktree or submodule) and `core.hooksPath` is unset, so no other hook manager owns the hooks;
- none of the paths fieldbook writes (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.gitignore`, `.cursor/`, `.github/`, `.clinerules`, `.git/hooks/` and the rest) is a symlink or contains one.

It is started from `~/.fieldbook/bin/fieldbook` as recorded at install time, with a fixed PATH and the same git overrides the engine uses. `FIELDBOOK_CMD` is honoured for manual commands only. A failed run is retried after 6 hours. When fieldbook is missing or blocked, the engine still writes its own files and says why once, in the result and the changelog; a manual command says it every time.

## Hostile folders

A downloaded or cloned folder controls every file name inside it and may carry its own git config.

- Every read and write inside a project goes through `engine/safefs.py`: paths are walked from the project root without following symlinks, reads accept regular UTF-8 files of at most 1 MB and never block on a FIFO or device, and writes go to a temp file that is renamed into place, so a symlink at the destination is replaced, never followed.
- Every git command goes through `engine/gitsafe.py`: an absolute git binary, started outside the folder, with the settings that can make read commands run programs (signature checking, fsmonitor, hooks, pagers, ssh) overridden and lazy fetches off. The engine uses only commands that read objects, refs and ignore rules (`config --get`, `rev-parse`, `log`, `ls-files`, `check-ignore --no-index`). It never runs `status`, `diff` or `add`, because those can start a filter program named in the repo's config that no override covers. One setup or `harness remove` lists tracked files with `ls-files` at most once and answers every name it needs from that listing, so a slow repository costs one listing per run, not one per name.
- Whether a file matches the committed version is worked out in Python from the blob hash, not by git.
- The triggers run with a fixed system PATH. The two Python hooks for Claude Code are registered with an absolute interpreter; the shell hooks and the git hooks start from `/bin/bash` and drop every empty or relative PATH entry before running anything, so a program planted in a repository is not picked up. The Claude Code shell hooks leave the project folder first and run their inline Python in isolated mode, so a `json.py` planted in a repository is not imported either. The `harness` command resolves the folder it was given, then leaves it before doing any work.
- A folder whose path holds a control character (a line break, say) is never set up or trusted: such a name could forge lines in the files the engine keeps.
- Deciding whether a folder holds several projects reads a bounded number of entries, so a very wide folder cannot make every trigger slow; one too wide to judge is left alone.
- No text from a project reaches the generated block or Claude's context except stack names and command keys from fixed lists and a workspace folder name restricted to plain characters.
- An untrusted repo gets local mode only: no tracked file is written, no hook is installed, and fieldbook is not run. Its `AGENTS.md` is imported for Claude Code only when it is a regular file inside the project with no `@` character in it at all, not even in an e-mail address: Claude Code can load whatever follows an `@` as a file, and how its Markdown reader splits text (escapes, emphasis) is its own business, so the engine does not try to tell references from other uses. An `AGENTS.md` with an `@` is not imported, and Claude Code will not see it in that repo unless you add `@AGENTS.md` to `CLAUDE.local.md` yourself. A change to `AGENTS.md` is checked again at the next trigger. Some git commands fire no hook at all (`git reset --hard`, `git restore`, `git stash pop`), so an `AGENTS.md` they bring in stays imported, if it was before, until the next Claude Code session start, checkout, pull or `cd` into that folder. A session that is already open keeps what it loaded, and a `.harness/config.json` it ships is ignored when the engine skipped the project. A `.harness/AGENTS.md` that is already there at the engine's first local setup (a tarball that carries `.git`, say) is treated the same way: when it has an `@` outside the generated block, or does not start with the engine's header, `CLAUDE.local.md` never imports it, and the engine keeps refusing on later runs. Likewise a `CLAUDE.local.md` that is already there at the engine's first local setup came with the folder: the engine does not write its import into it and does not list it in `info/exclude`, so it still shows in `git status` as before, and the changelog says so. The block is then not loaded until you add `@.harness/AGENTS.md` to that file yourself; if you delete the file, the engine creates its own at the next run. The same check runs on every later run for a file the engine wrote: when a pull or an edit leaves an `@` outside the block or removes the header, the engine takes the import back out of `CLAUDE.local.md`.
- A folder without git that arrived with its files (it was not empty when the engine first saw it) is in full mode, but what it ships is not yours. Its `AGENTS.md` is imported only while it has no `@` outside the generated block; when one appears later, or the file's block markers are damaged, or it is no longer a regular file, the engine takes its import back out of `CLAUDE.md`. A `.fieldbook/` bank it ships is not named in the block and your `.harness/decisions.md` is not moved into it; decisions stay in `.harness/decisions.md`. A `.harness/decisions.md` that was already there at the engine's first setup, here or in an untrusted repo, is not named in the block either (unless it is still the engine's empty template); the changelog says so, and the file is left as it is.

Not covered: a process that swaps folders for symlinks while the engine is writing (there is a short window between the last check and the rename), a folder you trusted that later turns hostile, and whatever fieldbook itself does in a repository you trusted.

## Decision engine

`engine/decide.py`. Each question is a flag: is this statement true. Callers compute 0-1 signals in code; the engine combines them with a logistic formula from `config/decisions.json`, answers True, False or unsure (within 0.15 below the threshold), and logs the answer with the signals behind it.

| Question | Decides | Learned from |
|---|---|---|
| `is_project` | whether to set up a folder that has no git and no manifest | nothing: no outcome measures it reliably |
| `pointer_useful` | whether to add the "For this task" note to a prompt | whether, in the turn answering that prompt, Claude read a named rule or memory file, used a named skill, or ran a named subagent |
| `model_suggestion_useful` | whether to show a `[model-router]` note | whether your next turn ran on the suggested model |

`harness learn` runs at most once a day in the background from the session-start hook. It labels finished turns from Claude Code transcripts, refits the weights of the two learned questions when at least 60 outcomes exist, and rebuilds calibration. A refit trains on the oldest 70% of outcomes, is kept only when it lowers log loss on the newest 30% by more than 0.005, and moves no weight more than 1.5 from the configured value. Calibration blends the formula's probability with the observed hit rate of its range once that range has 30 outcomes, using the newest 200. Changes are written to `~/.ai-rules/logs/learn.log`. Rule text never changes automatically.

Limits worth knowing:

- Outcomes exist only where the engine acted. To see below the threshold, the two learned questions also act on 20% of unsure answers. Nothing is known about cases answered False.
- A pointer "hit" means Claude used what the note named, which is compliance, not proof the note helped.
- `harness eval` reports counts and, for labelled decisions only, the hit rate and calibration error.

## Token budget

`config/harness-budgets.json`:

- `session`: caps on what loads at every Claude Code session start: global rules 1,800, project rule files 1,500 (including `@` imports inside the project), skill, agent and command descriptions 2,000.
- `project_block`: 600 for the generated block.
- `tiers`: what `harness plan` may select per model tier.

`harness doctor` reports each against its cap, in either mode. It exits 1 when a cap is exceeded, the installed copy differs from the repo, or a Claude Code hook is not registered or not executable. It also shows whether the git template hooks and the zsh trigger are in place (the hooks count only when git's init.templateDir points at `~/.git-templates` and no global core.hooksPath or GIT_TEMPLATE_DIR replaces them; a commented-out trigger line does not count), without failing on them. It also reads your Claude Code transcripts for the median first-turn context in the project. Most of that is Claude Code itself, tool and MCP schemas, and plugins, which the engine does not control.

The global rules are a core of about 1,800 tokens that loads every session. `rules/detail/` (prose style, characters, comments, scaffolding, scope, tooling) loads only when the core points to it.

In Claude Code the prompt hook names rules, skills, subagents or memory files only when the prompt's own words point to items that were not named earlier in the session. With the shipped weights, three new items always get the note. Two get it too, except on a prompt under 60 characters that is not the first of the session, where the answer is unsure. One item is unsure on a first prompt of 60 characters or more and gets no note otherwise. An unsure answer is acted on 20% of the time, so the engine can learn from it. Always-on items are never repeated there.

## Self-updating

- Projects regenerate when a manifest, lockfile, `Makefile`, CI or database folder, `AGENTS.md` or `CLAUDE.md` presence, fieldbook, git activity (commit, checkout, pull, config change) or the engine version changes.
- The install: at session start, at most once an hour, the engine re-runs `install.sh` in the background when all of these hold: the last install was made from a clean commit, the repo is on the same branch, its HEAD is a descendant of the installed commit, every commit since then was made in this checkout (read from the reflog), the tree is clean, and no other install is running. Another branch, an older commit, a rewritten history, and commits that arrived by pull, merge, cherry-pick or rebase are never installed automatically: after a pull, run `./install.sh` yourself. The engine never pulls. This is a check on how HEAD moved, not on where the content came from: a commit you make here is installed whatever is in it, including a squash merge or files checked out from another branch.
- `harness doctor` shows drift between the installed copy and the repo, and says when automatic updates are off because the last install came from uncommitted changes.

## Switches

- `touch ~/.ai-rules/harness.off` or `AI_HARNESS_OFF=1`: no setup, no notes, no background learning or updating. `harness init` and `harness trust` set nothing up either and say why. The write guard and the git hygiene hooks are separate and keep working.
- `touch ~/.ai-rules/router.off` or `AI_ROUTER_OFF=1`: no model notes or task notes in Claude Code. Project setup still runs.
- `.harness-skip` in a project, or a line in `~/.ai-rules/harness-exclude`: leave that project alone.

## Files under ~/.ai-rules

| Path | What |
|---|---|
| `releases/`, `current` | installed copies; `bin`, `engine`, `rules`, `config`, `skills`, `shell`, `agents`, `RULES.md` are links into `current`, so an install switches all of them at once. The newest three are kept |
| `harness-exclude`, `trusted` | yours to edit; never overwritten by the installer. `trusted` is also written by `harness trust`, `harness untrust` and the born-here rule |
| `data/` | learned weights, calibration, per-project state (keyed by the folder's device and inode, so a new folder at an old path starts fresh), locks |
| `state/` | per-session state for the Claude Code hooks, removed after 7 days |
| `logs/` | `decisions.jsonl`, `outcomes.jsonl`, `routing.jsonl`, `learn.log`, `learn-runs.log`, `self-update.log`. `decisions.jsonl` and `outcomes.jsonl` rotate at about 2 MB and `routing.jsonl` at about 1 MB; the five newest rotated files of each are kept. None holds prompt text. The decision log holds project paths, transcript paths and session ids |
| `source`, `installed-commit`, `installed-branch`, `fieldbook-path` | recorded at install |

## Tests

```bash
python3 -m unittest discover -s tests
```

The suite runs `install.sh`, the hooks and the CLI for real against a temporary home, and uses real git repositories. It takes about seven minutes.
