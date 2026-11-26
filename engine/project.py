"""Find the project a directory belongs to, and read its stack and commands.

A project is a root folder, not any folder. Git is not required. The home
folder, the standard folders in it, anything under ~/Library, and folders that
only hold other projects ("containers") are never projects, because rule files
written there would load into every project below.

Everything read from a project goes through safefs, and every git call through
gitsafe, because the folder may be hostile. Nothing in a repository can prove whose
it is (commit authors are forgeable), so trust comes only from the user's own list.
"""
from __future__ import annotations

import fcntl
import fnmatch
import json
import os
import re
from pathlib import Path

from . import safefs

MANIFESTS = {
    "package.json": ["nodejs"],
    "tsconfig.json": ["typescript"],
    "deno.json": ["deno"],
    "deno.jsonc": ["deno"],
    "pyproject.toml": ["python"],
    "requirements.txt": ["python"],
    "setup.py": ["python"],
    "setup.cfg": ["python"],
    "Pipfile": ["python"],
    "Cargo.toml": ["rust"],
    "go.mod": ["go"],
    "pom.xml": ["java"],
    "build.gradle": ["java"],
    "build.gradle.kts": ["kotlin"],
    "build.sbt": ["scala"],
    "Gemfile": ["ruby"],
    "composer.json": ["php"],
    "Package.swift": ["swift"],
    "pubspec.yaml": ["dart"],
    "mix.exs": ["elixir"],
    "CMakeLists.txt": ["cpp"],
    "Dockerfile": ["docker"],
    "docker-compose.yml": ["docker"],
    "docker-compose.yaml": ["docker"],
    "compose.yaml": ["docker"],
    "compose.yml": ["docker"],
}
GLOB_MANIFESTS = {".csproj": "dotnet", ".fsproj": "dotnet", ".sln": "dotnet"}
STAMP_FILES = list(MANIFESTS) + ["AGENTS.md", "Makefile", "Rakefile", "mypy.ini", "package-lock.json", "pnpm-lock.yaml",
                                 "yarn.lock", "bun.lock", "bun.lockb", "uv.lock", "poetry.lock", "mvnw", "gradlew"]
EXISTENCE_ONLY = [".github/workflows", "migrations", "prisma", "alembic", "CLAUDE.md",
                  ".claude/CLAUDE.md", ".fieldbook/config.yml", ".fieldbook/bank/04-decisions.md"]
DB_DIRS = ("migrations", "prisma", "alembic")
HOME_CONTAINERS = {"desktop", "documents", "downloads", "movies", "music", "pictures", "public", "applications",
                   "developer", "projects", "code", "src", "dev", "repos", "sites", "work", "github", "git",
                   "workspace", "workspaces"}
SKIP_PARTS = {"node_modules", "vendor", "venv", "__pycache__", "dist", "build", "target"}
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".rs", ".go", ".java", ".kt", ".rb", ".php",
            ".swift", ".c", ".cc", ".cpp", ".h", ".cs", ".dart", ".sh", ".ex", ".exs", ".scala"}
ENGINE_FILES = {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SCAN_LIMIT = 400        # child folders examined per directory
ENTRY_LIMIT = 4000      # entries read per directory before giving up
GRANDCHILD_ENTRIES = 64 # entries read in each grandchild when looking for a project marker
DEEP_LOOK_LIMIT = 300   # grandchild folders examined when deciding whether a folder holds several projects


def canonical(path):
    """The path with symlinks resolved and, where the system can say, the letter case it has on disk.

    On a case-insensitive disk ~/documents/repo and ~/Documents/Repo are one folder. Trust,
    excludes and container names are compared as text, so they need one spelling. macOS
    reports it through F_GETPATH; elsewhere the resolved path is used as is.
    """
    resolved = os.path.realpath(str(path))
    getpath = getattr(fcntl, "F_GETPATH", None)
    if getpath is None:
        return Path(resolved)
    try:
        fd = os.open(resolved, os.O_RDONLY | os.O_NONBLOCK)      # a FIFO at a remembered path must not hang us
    except OSError:
        return Path(resolved)
    try:
        true = fcntl.fcntl(fd, getpath, bytes(1024)).split(b"\0", 1)[0].decode("utf-8")
        return Path(true) if true else Path(resolved)
    except (OSError, UnicodeDecodeError):
        return Path(resolved)
    finally:
        os.close(fd)


def home():
    return canonical(Path.home())


def _glob_manifest(d, limit=None):
    limit = ENTRY_LIMIT if limit is None else limit
    try:
        with os.scandir(d) as it:
            for i, entry in enumerate(it):
                if i >= limit:
                    break
                ext = os.path.splitext(entry.name)[1]
                if ext in GLOB_MANIFESTS and entry.is_file(follow_symlinks=False):
                    return GLOB_MANIFESTS[ext]
    except OSError:
        pass
    return None


def has_manifest(d, limit=None):
    return any(os.path.lexists(os.path.join(d, m)) for m in MANIFESTS) or _glob_manifest(d, limit) is not None


def _git_dir(d):
    return os.path.isdir(os.path.join(d, ".git")) and not os.path.islink(os.path.join(d, ".git"))


def has_marker(d, limit=None):
    return os.path.lexists(os.path.join(d, ".git")) or has_manifest(d, limit)


def _child_dirs(d, limit=None):
    """(non-hidden real child folders, truncated). Filtering happens before the cap."""
    out, truncated = [], False
    limit = ENTRY_LIMIT if limit is None else limit
    try:
        with os.scandir(d) as it:
            for i, entry in enumerate(it):
                if i >= limit:
                    truncated = True
                    break
                if not entry.name.startswith(".") and entry.is_dir(follow_symlinks=False):
                    out.append(Path(entry.path))
                    if len(out) >= SCAN_LIMIT:
                        truncated = True
                        break
    except OSError:
        pass
    return out, truncated


def _count_projects(d, stop=2):
    """Projects among d's children, looking one level further into children without a marker.

    The look further down has a fixed budget, so a folder holding hundreds of folders of
    folders cannot make every trigger slow. Running out counts as "several projects": a
    folder that wide is not set up as one.
    """
    kids, _ = _child_dirs(d)
    n, budget = 0, DEEP_LOOK_LIMIT
    for k in kids:
        if has_marker(k, limit=GRANDCHILD_ENTRIES * 4):
            n += 1
        else:
            # Each child is read only as far as the folders the budget still allows, and a
            # child with more entries than that counts against it in full.
            grand, cut = _child_dirs(k, limit=max(budget, 1) * 4)
            if cut:
                return stop
            for g in grand:
                budget -= 1
                if budget < 0:
                    return stop
                if has_marker(g, limit=GRANDCHILD_ENTRIES):
                    n += 1
                    if n >= stop:
                        return n
        if n >= stop:
            return n
    return n


def is_container(d):
    """Home, its standard folders, and folders that hold several projects."""
    d = Path(d)
    h = home()
    if d == h or (d.parent == h and d.name.lower() in HOME_CONTAINERS):
        return True
    kids, truncated = _child_dirs(d)
    if truncated and not has_marker(d):
        return True                     # too large to judge and nothing says it is one project
    # Two real repos inside means a folder of projects, even with a stray manifest or its own .git.
    if sum(1 for k in kids if _git_dir(k)) >= 2:
        return True
    if os.path.lexists(os.path.join(d, ".git")) or has_manifest(d):
        return False
    return _count_projects(d) >= 2


def locate(cwd):
    """Return (root, why). root is None when cwd belongs to no project.

    Order: the git root (unless it is a container), else the highest folder with a
    manifest below the nearest container, else a workspace folder wrapping one
    project, else the folder directly below the nearest container or home.
    A folder inside a project's dependency or build folder is never a project.
    """
    p = canonical(cwd)
    try:
        rel = p.relative_to(home())
    except ValueError:
        return None, "outside home"
    if not rel.parts:
        return None, "home"
    if rel.parts[0].lower() == "library":
        return None, "library"
    if any(part.startswith(".") for part in rel.parts):
        return None, "hidden path"
    if not str(p).isprintable():
        return None, "control character in the path"     # such a name could forge lines in the files the engine keeps
    chain = [p] + list(p.parents)[: len(rel.parts) - 1]
    for a in chain:
        if a.name.lower() in SKIP_PARTS and has_marker(a.parent):
            return None, "dependency or build folder"
    for a in chain:
        if os.path.lexists(a / ".git"):
            if not is_container(a):
                return a, "git"
            break
    limit = len(chain)
    for i, a in enumerate(chain):
        # A folder of packages inside a manifest project (mono/packages) is part of that project.
        if is_container(a) and not any(has_manifest(b) and not is_container(b) for b in chain[i + 1:]):
            if i == 0:
                return None, "container"
            limit = i
            break
    below = chain[:limit]
    for a in reversed(below):
        if has_manifest(a):
            return a, "manifest"
    for a in reversed(below):
        if code_root(a)[0] != a:
            return a, "workspace"
    return below[-1], ("under container" if limit < len(chain) else "top-level")


def load_excludes(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").split("\n")
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(str(canonical(os.path.expanduser(line))) if not any(c in line for c in "*?[") else _canonical_glob(line))
    return out


def _canonical_glob(pattern):
    """A glob with the part before its first wildcard folder spelled as on disk, so a pattern
    written through a symlinked home, or in another letter case, still matches."""
    parts = Path(os.path.expanduser(pattern)).parts
    fixed = 0
    while fixed < len(parts) and not any(c in parts[fixed] for c in "*?["):
        fixed += 1
    base = canonical(Path(*parts[:fixed])) if fixed else Path()
    return str(base.joinpath(*parts[fixed:]))


def _glob_match(path, pattern):
    """fnmatch, ignoring letter case where the disk does."""
    if fnmatch.fnmatchcase(path, pattern):
        return True
    return getattr(fcntl, "F_GETPATH", None) is not None and fnmatch.fnmatchcase(path.lower(), pattern.lower()) \
        and _same_ignoring_case(path)


def _same_ignoring_case(path):
    """True when this disk treats the path's other letter cases as the same file."""
    swapped = path.swapcase()
    try:
        return swapped != path and os.path.samefile(path, swapped)
    except OSError:
        return False


def is_excluded(root, patterns, skip_file=True):
    s = str(canonical(root))
    for pat in patterns:
        pat = pat.rstrip("/")
        if s == pat or s.startswith(pat + "/") or _glob_match(s, pat):
            return True
    return skip_file and os.path.lexists(os.path.join(root, ".harness-skip"))


def code_root(root):
    """(folder holding the code, command prefix). A workspace wrapping exactly one project reads from it.

    The inner folder's name ends up in AGENTS.md and in commands, so only plain names qualify.
    """
    if has_marker(root):
        return root, ""
    kids, _ = _child_dirs(root)
    marked = [k for k in kids if has_marker(k)]
    if len(marked) == 1 and SAFE_NAME.match(marked[0].name):
        return marked[0], "cd %s && " % marked[0].name
    return root, ""


def is_workspace(root):
    return code_root(root)[0] != root


def _read_json(root, name):
    text = safefs.read_text(root, root / name)
    if text is None:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except (ValueError, RecursionError):      # deep nesting overflows the parser's stack
        return {}


def _read(root, name):
    return safefs.read_text(root, root / name) or ""


def _dict(value):
    return value if isinstance(value, dict) else {}


def detect_tags(root):
    root = code_root(root)[0]
    tags = set()
    for name, found in MANIFESTS.items():
        if os.path.lexists(root / name):
            tags.update(found)
    glob = _glob_manifest(root)
    if glob:
        tags.add(glob)
    pkg = _read_json(root, "package.json")
    deps = dict(_dict(pkg.get("dependencies")))
    deps.update(_dict(pkg.get("devDependencies")))
    if "react" in deps:
        tags.add("react")
    if "typescript" in deps:
        tags.add("typescript")
    if "nodejs" in tags and "typescript" not in tags:
        tags.add("javascript")
    if "dart" in tags and re.search(r"(?m)^[ \t]{0,40}flutter[ \t]{0,8}:", _read(root, "pubspec.yaml")):
        tags.add("flutter")
    if safefs.is_dir(root, root / ".github" / "workflows"):
        tags.add("ci")
    if any(safefs.is_dir(root, root / d) for d in DB_DIRS):
        tags.add("database")
    return sorted(tags)


def package_manager(root):
    root = code_root(root)[0]
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun"),
                     ("package-lock.json", "npm")):
        if os.path.lexists(root / lock):
            return pm
    declared = _read_json(root, "package.json").get("packageManager")
    if isinstance(declared, str):
        name = declared.split("@", 1)[0]
        if name in ("npm", "pnpm", "yarn", "bun"):
            return name
    return "npm" if os.path.lexists(root / "package.json") else ""


def _code_lines(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _mentions(text, word):
    return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(word), text) is not None


def _executable(path):
    return os.path.isfile(path) and os.access(path, os.X_OK) and not os.path.islink(path)


def detect_commands(root):
    """Commands read from the project's own files. Nothing is listed that the files do not define."""
    root, prefix = code_root(root)
    cmds = {}
    pm = package_manager(root)
    scripts = _dict(_read_json(root, "package.json").get("scripts"))
    for key in ("test", "build", "lint", "typecheck", "format", "dev", "start"):
        value = scripts.get(key)
        if isinstance(value, str) and "no test specified" not in value:
            cmds[key] = "%s run %s" % (pm, key)

    deno = _read_json(root, "deno.json") or _read_json(root, "deno.jsonc")
    for key in ("test", "build", "lint", "fmt", "dev", "start"):
        if isinstance(_dict(deno.get("tasks")).get(key), str):
            cmds.setdefault("format" if key == "fmt" else key, "deno task %s" % key)

    composer = _dict(_read_json(root, "composer.json").get("scripts"))
    for key in ("test", "lint", "build"):
        if key in composer:
            cmds.setdefault(key, "composer run %s" % key)

    makefile = "\n".join(l[:300] for l in _read(root, "Makefile").split("\n"))     # a target line is short
    for line in re.findall(r"(?m)^([A-Za-z][\w.-]{0,80}(?:[ \t]{1,8}[A-Za-z][\w.-]{0,80}){0,20})[ \t]{0,8}:(?![=:])", makefile):
        for target in line.split():
            if target in ("test", "build", "lint", "check", "format", "fmt"):
                cmds.setdefault("format" if target == "fmt" else target, "make %s" % target)

    py = _code_lines(_read(root, "pyproject.toml") + "\n" + _read(root, "requirements.txt") + "\n"
                     + _read(root, "setup.cfg") + "\n" + _read(root, "Pipfile"))
    if py.strip():
        run = ("uv run " if os.path.lexists(root / "uv.lock") else
               "poetry run " if os.path.lexists(root / "poetry.lock") else
               "pipenv run " if os.path.lexists(root / "Pipfile") else "")
        if _mentions(py, "pytest"):
            cmds.setdefault("test", run + "pytest")
        if _mentions(py, "ruff"):
            cmds.setdefault("lint", run + "ruff check .")
        if "[tool.mypy]" in py or os.path.lexists(root / "mypy.ini"):
            cmds.setdefault("typecheck", run + "mypy .")

    if os.path.lexists(root / "Cargo.toml"):
        cmds.setdefault("test", "cargo test")
        cmds.setdefault("build", "cargo build")
    if os.path.lexists(root / "go.mod"):
        cmds.setdefault("test", "go test ./...")
        cmds.setdefault("build", "go build ./...")
    if os.path.lexists(root / "pom.xml"):
        mvn = "./mvnw" if _executable(root / "mvnw") else "mvn"
        cmds.setdefault("test", mvn + " test")
        cmds.setdefault("build", mvn + " package")
    if os.path.lexists(root / "build.gradle") or os.path.lexists(root / "build.gradle.kts"):
        gradle = "./gradlew" if _executable(root / "gradlew") else "gradle"
        cmds.setdefault("test", gradle + " test")
        cmds.setdefault("build", gradle + " build")
    if os.path.lexists(root / "build.sbt"):
        cmds.setdefault("test", "sbt test")
    if _glob_manifest(root) == "dotnet":
        cmds.setdefault("test", "dotnet test")
        cmds.setdefault("build", "dotnet build")
    if os.path.lexists(root / "Package.swift"):
        cmds.setdefault("test", "swift test")
        cmds.setdefault("build", "swift build")
    if os.path.lexists(root / "pubspec.yaml"):
        cmds.setdefault("test", "flutter test" if "flutter" in detect_tags(root) else "dart test")
    if os.path.lexists(root / "mix.exs"):
        cmds.setdefault("test", "mix test")
    if _mentions(_code_lines(_read(root, "Gemfile")), "rspec"):
        cmds.setdefault("test", "bundle exec rspec")
    return {k: prefix + v for k, v in cmds.items()}


def identity(path):
    """A folder's device, inode and, where the system records one, creation time, as text; ""
    when it cannot be read. The creation time tells a new folder from a deleted one whose
    inode number the disk gave out again."""
    try:
        st = os.stat(path)
    except OSError:
        return ""
    born = getattr(st, "st_birthtime", None)
    return "%d-%d" % (st.st_dev, st.st_ino) + ("-%d" % int(born * 1000) if born else "")


def load_trusted(path):
    """{project root: identity or None} for the folders the user trusts.

    A line is a folder, optionally followed by a tab and the folder's identity. Lines the
    engine writes carry the identity, so a different folder that later appears at the same
    path is not trusted. A line written by hand has none and is matched by path alone.
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").split("\n")     # only a real newline ends an entry
    except OSError:
        return {}
    out = {}
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        folder, _, ident = line.partition("\t")
        out[str(canonical(os.path.expanduser(folder.strip())))] = ident.strip() or None
    return out


def _listed(path, trusted):
    path = str(canonical(path))
    if path not in trusted:
        return False
    return trusted[path] is None or trusted[path] == identity(path)


def enclosing_repo(root):
    """The nearest folder at or above root, inside home, that has a .git entry, or None."""
    root = Path(root)
    h = home()
    for a in [root] + list(root.parents):
        if a == h or h not in a.parents:
            return None
        if os.path.lexists(a / ".git"):
            return a
    return None


def is_trusted(root, trusted):
    """True when the repository holding root, or the repository a worktree belongs to, is on the list."""
    repo = enclosing_repo(root) or Path(root)
    if _listed(repo, trusted):
        return True
    layout = git_layout(repo)
    if layout and layout[0] != layout[1] and layout[1].name == ".git":      # a worktree of a trusted repo
        return _listed(layout[1].parent, trusted)
    return False


def _same(a, b):
    """True when two paths are one file or folder, however they are spelled."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def git_layout(root):
    """(git dir, common dir) when the checkout's git folder provably belongs to it, else None.

    A real .git folder qualifies. A .git file (worktree or submodule) qualifies only when
    the folder it names points back at this checkout, because a hostile .git file can name
    any repository on the machine.
    """
    root = Path(root)
    dot = root / ".git"
    if not os.path.lexists(dot):
        return None
    if os.path.isdir(dot) and not os.path.islink(dot):
        return dot, dot
    if os.path.islink(dot) or not os.path.isfile(dot):
        return None
    raw = safefs.read_small(dot, 4096)
    if not raw or not raw.startswith(b"gitdir:"):
        return None
    try:
        named = raw[len(b"gitdir:"):].decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    gitdir = Path(os.path.realpath(named if os.path.isabs(named) else os.path.join(root, named)))
    inside = Path(os.path.realpath(root))
    # Compared by identity: realpath keeps the letter case it was given, so ../EVIL/gd from
    # folder evil/ would pass a text comparison on a case-folding disk.
    if any(_same(inside, p) for p in (gitdir,) + tuple(gitdir.parents)):
        return None                       # a git folder among the checkout's own files: its index can track info/exclude
    back =safefs.read_small(gitdir / "gitdir", 4096)          # worktree: <common>/worktrees/<name>/gitdir
    common_ref = safefs.read_small(gitdir / "commondir", 4096)
    if back and common_ref:
        try:
            back_path = os.path.realpath(back.decode("utf-8").strip())
            common = Path(os.path.realpath(os.path.join(gitdir, common_ref.decode("utf-8").strip())))
        except UnicodeDecodeError:
            return None
        if not any(_same(inside, p) for p in (common,) + tuple(common.parents)) and _same(back_path, dot) \
                and _same(gitdir.parent, common / "worktrees") and _git_dir_like(common, inside):
            return gitdir, common
        return None
    worktree = _core_worktree(safefs.read_small(gitdir / "config", 65536))      # submodule
    if worktree and _same(os.path.join(gitdir, worktree), root):
        return gitdir, gitdir
    return None


def _git_dir_like(common, inside):
    """True when a worktree's common dir is a real git directory: a .git folder, or a bare
    repository that does not hold the checkout. commondir "../.." can otherwise name an
    ordinary folder such as ~/Downloads, and the engine would write its info/exclude there.
    The name alone is not enough: an unpacked download can hold any folder called .git."""
    if not (os.path.isfile(common / "HEAD") and os.path.isdir(common / "objects") and os.path.isdir(common / "refs")):
        return False
    return common.name == ".git" or not any(_same(common, p) for p in inside.parents)


def _core_worktree(raw):
    """core.worktree from a git config file's bytes, read here so no git runs on a folder not yet verified."""
    if not raw:
        return ""
    section = ""
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
        elif section == "core" and "=" in line:
            key, value = line.split("=", 1)
            if key.strip().lower() == "worktree":
                return value.strip().strip('"')
    return ""


def is_empty(root):
    """True when the folder holds nothing at all, dotfiles included. A Finder .DS_Store does not count.

    shape() skips dotfiles and the engine's own file names, which a download can carry too."""
    try:
        with os.scandir(root) as it:
            return all(e.name == ".DS_Store" and e.is_file(follow_symlinks=False) for e in it)
    except OSError:
        return False


def shape(root):
    """Cheap facts about a folder with no project marker: is someone building something here?"""
    entries = code = 0
    has_src = False
    subs = []
    try:
        with os.scandir(root) as it:
            for i, entry in enumerate(it):
                if i >= ENTRY_LIMIT:
                    break
                if entry.name.startswith(".") or entry.name in ENGINE_FILES:
                    continue
                entries += 1
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in ("src", "app", "lib"):
                        has_src = True
                        subs.append(entry.path)
                elif os.path.splitext(entry.name)[1] in CODE_EXT:
                    code += 1
    except OSError:
        pass
    for sub in subs:
        try:
            with os.scandir(sub) as it:
                for i, e in enumerate(it):
                    if i >= SCAN_LIMIT:
                        break
                    if os.path.splitext(e.name)[1] in CODE_EXT and e.is_file(follow_symlinks=False):
                        code += 1
        except OSError:
            pass
    return {"entries": entries, "code_files": code, "has_src": has_src}


def _stat_parts(base, label):
    parts = []
    for name in STAMP_FILES:
        try:
            st = os.lstat(base / name)
            parts.append("%s%s:%d:%d" % (label, name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    for name in EXISTENCE_ONLY:
        if os.path.lexists(base / name):
            parts.append("%s%s" % (label, name))
    glob = _glob_manifest(base)
    if glob:
        parts.append("%sglob:%s" % (label, glob))
    return parts


def stamp(root):
    """Changes whenever something that feeds generation changes. Cheap enough to run on every cd.

    Git activity (commits, checkouts, pulls, config and info/exclude edits) is included so that
    a repo turning shared, a branch switch, or an ignore rule you add, is noticed without a
    manifest change.
    """
    root = Path(root)
    code, _ = code_root(root)
    parts = _stat_parts(root, "")
    if code != root:
        parts += _stat_parts(code, code.name + "/")
    parts.append("git:%d" % os.path.lexists(root / ".git"))
    layout = git_layout(root)
    if layout:
        for base, names in ((layout[0], ("HEAD", "logs/HEAD", "FETCH_HEAD")), (layout[1], ("config", "info/exclude"))):
            for name in names:
                try:
                    parts.append("git/%s:%d" % (name, os.lstat(base / name).st_mtime_ns))
                except OSError:
                    pass
    if not has_marker(root) and code == root:
        s = shape(root)
        parts.append("shape:%d:%d:%d" % (min(s["entries"], 50), min(s["code_files"], 50), s["has_src"]))
    return "|".join(parts)
