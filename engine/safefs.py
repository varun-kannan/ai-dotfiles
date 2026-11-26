"""File access inside a project that a hostile repository cannot redirect.

A cloned repository controls every name under its root, so any path the engine
reads or writes there could be a symlink to ~/.zshrc, /dev/zero, a FIFO, or a
folder outside the project. Every project read and write goes through here.

Paths are walked one component at a time from an open handle on the root, with
O_NOFOLLOW, so a symlink anywhere below the root is refused and a component
swapped for a symlink mid-walk is refused too. Reads accept regular files only,
capped in size, and never block on a FIFO. Writes go to a temp file created
inside the already-open parent folder and are renamed into place, so an existing
symlink at the destination is replaced, never followed.

Python 3.9 on macOS has no rename relative to a folder handle, so the rename uses
the path, after checking that the path still names the folder that was opened.
The remaining window needs a live attacker process racing the rename.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_READ = 1_000_000
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


class Unsafe(Exception):
    """A path under the project root that the engine refuses to touch."""


def _parts(root, path):
    root = Path(root)
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    try:
        rel = path.relative_to(root)
    except ValueError:
        raise Unsafe("outside the project: %s" % path)
    if ".." in rel.parts or not rel.parts:
        raise Unsafe("not a path inside the project: %s" % path)
    return rel.parts


def inside(root, path):
    """Absolute path if it is under root with no symlinked component that exists."""
    parts = _parts(root, path)
    cur = Path(root)
    for part in parts:
        cur = cur / part
        try:
            if stat.S_ISLNK(os.lstat(cur).st_mode):
                raise Unsafe("symlink in project path: %s" % cur)
        except FileNotFoundError:
            break
    return Path(root).joinpath(*parts)


def _open_parent(root, parts, create=False):
    """Open the folder holding the last component, walking from root without following links."""
    fd = os.open(str(root), _DIR_FLAGS)
    try:
        for part in parts[:-1]:
            try:
                nxt = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o755, dir_fd=fd)
                nxt = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                raise Unsafe("cannot enter %s: %s" % (part, exc))
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def _lstat_at(fd, name):
    try:
        return os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def read_small(path, limit=65536):
    """Bytes of a regular file at an absolute path, final component not followed, or None."""
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            return None
        return os.read(fd, limit)
    except OSError:
        return None
    finally:
        os.close(fd)


def read_text(root, path, limit=MAX_READ):
    """Text of a regular UTF-8 file under root, or None when missing, not regular, too big,
    not valid UTF-8, or unsafe. Invalid bytes are never replaced: a file the engine cannot
    decode exactly is a file it must not rewrite."""
    data = read_bytes(root, path, limit)
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def read_bytes(root, path, limit=MAX_READ):
    """Bytes of a regular file under root, or None when missing, not regular, too big, or unsafe."""
    try:
        parts = _parts(root, path)
        fd = _open_parent(root, parts)
    except (Unsafe, OSError):
        return None
    try:
        try:
            ffd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except OSError:
            return None
        try:
            st = os.fstat(ffd)
            if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
                return None
            chunks, total = [], 0
            while True:
                chunk = os.read(ffd, 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(ffd)
    finally:
        os.close(fd)


def exists(root, path):
    try:
        parts = _parts(root, path)
        fd = _open_parent(root, parts)
    except (Unsafe, OSError):
        return False
    try:
        return _lstat_at(fd, parts[-1]) is not None
    finally:
        os.close(fd)


def is_regular(root, path):
    try:
        parts = _parts(root, path)
        fd = _open_parent(root, parts)
    except (Unsafe, OSError):
        return False
    try:
        st = _lstat_at(fd, parts[-1])
        return st is not None and stat.S_ISREG(st.st_mode)
    finally:
        os.close(fd)


def is_dir(root, path):
    try:
        parts = _parts(root, path)
        fd = _open_parent(root, parts)
    except (Unsafe, OSError):
        return False
    try:
        st = _lstat_at(fd, parts[-1])
        return st is not None and stat.S_ISDIR(st.st_mode)
    finally:
        os.close(fd)


def write_text(root, path, text):
    """Atomically write a file under root. A symlink at the destination is replaced, not followed."""
    parts = _parts(root, path)
    fd = _open_parent(root, parts, create=True)
    try:
        name = parts[-1]
        st = _lstat_at(fd, name)
        if st is not None and stat.S_ISDIR(st.st_mode):
            raise Unsafe("a folder is in the way: %s" % name)
        mode = stat.S_IMODE(st.st_mode) if st is not None and stat.S_ISREG(st.st_mode) else 0o644
        tmp = ".%s.%d.tmp" % (name, os.getpid())
        tfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=fd)
        try:
            data = text.encode("utf-8")
            view = memoryview(data)
            while view:
                view = view[os.write(tfd, view):]
        finally:
            os.close(tfd)
        parent = Path(root).joinpath(*parts[:-1])
        opened = os.fstat(fd)
        try:
            now = os.lstat(parent)
            if (now.st_dev, now.st_ino) != (opened.st_dev, opened.st_ino) or stat.S_ISLNK(now.st_mode):
                raise Unsafe("folder changed during write: %s" % parent)
            os.replace(str(parent / tmp), str(parent / name))
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=fd)
            except OSError:
                pass
            raise
        return parent / name
    finally:
        os.close(fd)


def remove(root, path):
    """Remove a file or symlink under root (never what a symlink points to). False if absent."""
    parts = _parts(root, path)
    try:
        fd = _open_parent(root, parts)
    except FileNotFoundError:
        return False
    try:
        st = _lstat_at(fd, parts[-1])
        if st is None:
            return False
        if stat.S_ISDIR(st.st_mode):
            raise Unsafe("refusing to remove a folder as a file: %s" % parts[-1])
        os.unlink(parts[-1], dir_fd=fd)
        return True
    finally:
        os.close(fd)


def rmdir(root, path):
    """Remove an empty folder under root. False if absent or not empty."""
    parts = _parts(root, path)
    try:
        fd = _open_parent(root, parts)
    except FileNotFoundError:
        return False
    try:
        st = _lstat_at(fd, parts[-1])
        if st is None or not stat.S_ISDIR(st.st_mode):
            return False
        try:
            os.rmdir(parts[-1], dir_fd=fd)
            return True
        except OSError:
            return False
    finally:
        os.close(fd)
