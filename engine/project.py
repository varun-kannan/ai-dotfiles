"""Find the project a directory belongs to, and read its stack and commands.

A project is a root folder, not any folder. Git is not required. The home
folder and folders that only hold other projects ("containers") are never
projects, because rule files written there would load into every project below.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path

MANIFESTS = {
    "package.json": ["nodejs"],
    "tsconfig.json": ["typescript"],
    "pyproject.toml": ["python"],
    "requirements.txt": ["python"],
    "setup.py": ["python"],
    "Cargo.toml": ["rust"],
    "go.mod": ["go"],
    "pom.xml": ["java"],
    "build.gradle": ["java"],
    "build.gradle.kts": ["kotlin"],
    "Dockerfile": ["docker"],
    "docker-compose.yml": ["docker"],
    "compose.yaml": ["docker"],
}
# Files whose change can alter the stack or the commands. Part of the change stamp.
STAMP_FILES = list(MANIFESTS) + ["Makefile", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
                                 "uv.lock", "poetry.lock", "mvnw", "gradlew"]
DB_DIRS = ("migrations", "prisma", "alembic")
HOME_CONTAINERS = {"Desktop", "Documents", "Downloads", "Library", "Movies", "Music", "Pictures",
                   "Public", "Applications"}
SKIP_PARTS = {"node_modules", "vendor", "venv", "__pycache__", "dist", "build", "target"}
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".rs", ".go", ".java", ".kt", ".rb", ".php",
            ".swift", ".c", ".cc", ".cpp", ".h", ".cs", ".dart", ".sh"}
SCAN_LIMIT = 400


def home():
    return Path.home()


def has_manifest(d):
    return any((d / m).exists() for m in MANIFESTS)


def has_marker(d):
    return (d / ".git").exists() or has_manifest(d)


def _child_dirs(d):
    out = []
    try:
        with os.scandir(d) as it:
            for i, entry in enumerate(it):
                if i >= SCAN_LIMIT:
                    break
                if not entry.name.startswith(".") and entry.is_dir():
                    out.append(Path(entry.path))
    except OSError:
        pass
    return out


def is_container(d):
    """True for home, the standard folders under it, and folders that hold several projects."""
    h = home()
    if d == h or (d.parent == h and d.name in HOME_CONTAINERS):
        return True
    kids = _child_dirs(d)
    own_manifest = has_manifest(d)
    if not own_manifest and sum(1 for k in kids if (k / ".git").exists()) >= 2:
        return True
    if not own_manifest and not (d / ".git").exists():
        return sum(1 for k in kids if has_marker(k)) >= 2
    return False


def locate(cwd):
    """Return (root, why). root is None when cwd belongs to no project."""
    p = Path(cwd).resolve()
    try:
        rel = p.relative_to(home().resolve())
    except ValueError:
        return None, "outside home"
    if not rel.parts:
        return None, "home"
    if any(part.startswith(".") or part in SKIP_PARTS for part in rel.parts):
        return None, "hidden or dependency path"
    chain = [p] + list(p.parents)[: len(rel.parts) - 1]
    for a in chain:
        if (a / ".git").exists():
            if not is_container(a):
                return a, "git"
            break
    for i, a in enumerate(chain):
        if is_container(a):
            return (None, "container") if i == 0 else (chain[i - 1], "under container")
    return chain[-1], "top-level"


def load_excludes(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [os.path.expanduser(l.strip()) for l in lines if l.strip() and not l.lstrip().startswith("#")]


def is_excluded(root, patterns):
    s = str(root)
    for pat in patterns:
        pat = pat.rstrip("/")
        if s == pat or s.startswith(pat + "/") or fnmatch.fnmatch(s, pat):
            return True
    return (root / ".harness-skip").exists()


def detect_tags(root):
    tags = set()
    for name, found in MANIFESTS.items():
        if (root / name).exists():
            tags.update(found)
    pkg = _read_json(root / "package.json")
    deps = dict(pkg.get("dependencies") or {})
    deps.update(pkg.get("devDependencies") or {})
    if "react" in deps:
        tags.add("react")
    if "typescript" in deps:
        tags.add("typescript")
    if "nodejs" in tags and "typescript" not in tags:
        tags.add("javascript")
    if (root / ".github" / "workflows").is_dir():
        tags.add("ci")
    if any((root / d).is_dir() for d in DB_DIRS):
        tags.add("database")
    return sorted(tags)


def _read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def package_manager(root):
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lock", "bun"), ("bun.lockb", "bun")):
        if (root / lock).exists():
            return pm
    return "npm" if (root / "package.json").exists() else ""


def detect_commands(root):
    """Commands read from the project's own files. Nothing is listed that the files do not define."""
    cmds = {}
    pm = package_manager(root)
    scripts = _read_json(root / "package.json").get("scripts") or {}
    for key in ("test", "build", "lint", "typecheck", "format", "dev", "start"):
        value = scripts.get(key)
        if isinstance(value, str) and "no test specified" not in value:
            cmds[key] = "%s run %s" % (pm, key)

    for target in re.findall(r"^(test|build|lint|check|format|fmt)\s*:", _read(root / "Makefile"), re.M):
        cmds.setdefault("format" if target == "fmt" else target, "make %s" % target)

    py = _read(root / "pyproject.toml") + _read(root / "requirements.txt")
    if py:
        run = "uv run " if (root / "uv.lock").exists() else "poetry run " if (root / "poetry.lock").exists() else ""
        if "pytest" in py:
            cmds.setdefault("test", run + "pytest")
        if "ruff" in py:
            cmds.setdefault("lint", run + "ruff check .")
        if "[tool.mypy]" in py:
            cmds.setdefault("typecheck", run + "mypy .")

    if (root / "Cargo.toml").exists():
        cmds.setdefault("test", "cargo test")
        cmds.setdefault("build", "cargo build")
    if (root / "go.mod").exists():
        cmds.setdefault("test", "go test ./...")
        cmds.setdefault("build", "go build ./...")
    if (root / "pom.xml").exists():
        cmds.setdefault("test", ("./mvnw" if (root / "mvnw").exists() else "mvn") + " -q verify")
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        gradle = "./gradlew" if (root / "gradlew").exists() else "gradle"
        cmds.setdefault("test", gradle + " check")
        cmds.setdefault("build", gradle + " build")
    return cmds


def shape(root):
    """Cheap facts about a folder with no project marker: is someone building something here?"""
    entries = code = 0
    has_src = False
    try:
        with os.scandir(root) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                entries += 1
                if entries > SCAN_LIMIT:
                    break
                if entry.is_dir():
                    has_src = has_src or entry.name in ("src", "app", "lib")
                elif os.path.splitext(entry.name)[1] in CODE_EXT:
                    code += 1
    except OSError:
        pass
    for sub in ("src", "app", "lib"):
        try:
            with os.scandir(root / sub) as it:
                code += sum(1 for i, e in enumerate(it) if i < SCAN_LIMIT and os.path.splitext(e.name)[1] in CODE_EXT)
        except OSError:
            pass
    return {"entries": entries, "code_files": code, "has_src": has_src}


def stamp(root):
    """Changes whenever something that feeds generation changes. Cheap enough to run on every cd."""
    parts = []
    for name in STAMP_FILES:
        try:
            st = os.stat(root / name)
            parts.append("%s:%d:%d" % (name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    parts.append("git:%d" % (root / ".git").exists())
    parts.append("fb:%d" % (root / ".fieldbook" / "config.yml").exists())
    if not has_marker(root):
        s = shape(root)
        parts.append("shape:%d:%d" % (min(s["entries"], 50), min(s["code_files"], 50)))
    return "|".join(parts)
