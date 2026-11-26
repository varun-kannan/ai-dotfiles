#!/bin/bash
# hygiene:ignore-file - quotes the patterns it documents
# pre-write-guard.sh - Claude Code PreToolUse hook for Write|Edit|NotebookEdit.
#
# Blocks a write when the content carries a hard hygiene violation: hidden or
# invisible Unicode, curly quotes used as string delimiters in code, unfilled placeholders,
# elided code, or leaked generation scaffolding.
#
# Exit 2 prevents the tool call and feeds stderr back to the model, so it gets
# one chance to fix the content instead of the defect landing on disk.
#
# It fails open only where there is nothing to check with: no scanner installed, no python3,
# or hook input it cannot read. A scanner or guard that fails part way blocks (not-checked).
#
# CLAUDE.md sections 8, 11, 12.

# Only absolute PATH entries: an empty or relative one could pick up a program from the repo.
_p=""; _ifs="$IFS"; IFS=:
for _d in $PATH; do case "$_d" in /*) _p="${_p:+$_p:}$_d" ;; esac; done
IFS="$_ifs"; PATH="${_p:-/usr/bin:/bin}"; export PATH

HYGIENE="${CONTENT_HYGIENE_BIN:-${AI_RULES_HOME:-$HOME/.ai-rules}/bin/content-hygiene}"
[ -x "$HYGIENE" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# Hooks start in the project folder, which may hold look-alike programs and modules: leave it,
# and run Python isolated (-I) so nothing is imported from there. The hook input stays on
# stdin and the text to scan is piped to the scanner, so no command line limits the size (the
# scanner reads the first 2 MB).
# A relative tool path is read from where the hook started (the project), unless the hook input
# names its own cwd.
GUARD_CWD="$PWD"
cd / 2>/dev/null || exit 0
# The guard's own code is not trusted to be right: if it crashes (exit other than 0 or 2), the
# write is blocked rather than let through, since Claude Code reads any other exit as "go on".
GUARD_SECONDS="$SECONDS" GUARD_CWD="$GUARD_CWD" HYGIENE="$HYGIENE" python3 -I -c '
import array, bisect, difflib, errno, json, os, pickle, re, select, signal, subprocess, sys, threading, time

# The hook has 15 seconds. A guard that has not decided by 12 blocks the write as not checked,
# rather than let the hook time out, which lets the write through. The 12 count from when bash
# started (in whole seconds, so up to one short), leaving room for starting Python under load.
BUDGET = 12


def _out_of_time(signum, frame):
    sys.stderr.write("Blocked: the write guard could not finish checking this write in time (not-checked).\n")
    os._exit(2)


try:
    EARLIER = min(max(int(os.environ.get("GUARD_SECONDS") or 0), 0), 6)
except ValueError:
    EARLIER = 0
signal.signal(signal.SIGALRM, _out_of_time)
signal.setitimer(signal.ITIMER_REAL, BUDGET - EARLIER)
STARTED = time.monotonic() - EARLIER

MARKER = "hygiene:ignore-file"
try:
    hook = json.load(sys.stdin)
    tool_input = hook.get("tool_input") or {}
except (ValueError, AttributeError):
    sys.exit(0)
if not isinstance(tool_input, dict):
    sys.exit(0)
base_dir = hook.get("cwd") if isinstance(hook.get("cwd"), str) and hook["cwd"].startswith("/") \
    else os.environ.get("GUARD_CWD", "")


def text_of(d, keys):
    return [d[k] for k in keys if isinstance(d.get(k), str) and d[k]]


# Write gives the whole file (content, file_text). Edit and NotebookEdit give a fragment
# (new_string, new_source), and a multi-edit gives several (edits[].new_string).
path = (text_of(tool_input, ("file_path", "notebook_path")) or [""])[0]
if path and not path.startswith("/") and base_dir.startswith("/"):
    path = os.path.join(base_dir, path)   # not normalized: a ".." segment still loses any exemption
whole = text_of(tool_input, ("content", "file_text"))
parts = text_of(tool_input, ("new_string", "new_str", "new_source"))
for edit in tool_input.get("edits") if isinstance(tool_input.get("edits"), list) else []:
    if isinstance(edit, dict):
        parts += text_of(edit, ("new_string", "new_str", "new_source"))
body = whole[0] if whole else "\n".join(parts)
# An edit with empty new text (a deletion) is still judged in place: it can turn text into code.
if not body and not (isinstance(tool_input.get("old_string"), str) or isinstance(tool_input.get("edits"), list)):
    sys.exit(0)

# An edit is judged where it lands: the replacements are applied to the file on disk, and for
# each character of the result the guard keeps where it came from in the file (or -1 for new
# text). A line whose characters all come, in one run, from the file is unchanged, and the
# guard knows its old line number; every other line was changed by the edit. This costs one
# pass per edit, however repetitive the file. When the edit cannot be placed, the new text is
# scanned on its own.
in_place = None
edits = [e for e in tool_input.get("edits") if isinstance(e, dict)] if isinstance(tool_input.get("edits"), list) else []
if not whole and isinstance(tool_input.get("old_string"), str) and isinstance(tool_input.get("new_string"), str):
    edits = [tool_input] + edits
# Placing the edits may run until this many seconds before the budget ends: the rest is for the scans.
SCAN_RESERVE = 5
# The scanner reads the first 2000000 bytes of UTF-8: a file larger than that is not placed.
MAX_SCAN_BYTES = 2000000
# A multi-edit is refused as a whole when one of its edits does not fit what the edits before it
# left; a single edit that does not fit is judged on its new text alone.
MULTI = isinstance(tool_input.get("edits"), list)
# The line diffs of all the edits share one budget (line pairs and seconds): past it, an edit keeps
# only its shared start and end, which marks more lines changed but never fewer.
diff_budget = [300000, None]

def new_offsets(old_s, new_s):
    """For each character of new_s, its offset in old_s when it sits on a line the edit kept
    unchanged, else -1."""
    head = len(os.path.commonprefix([old_s, new_s]))
    tail = len(os.path.commonprefix([old_s[head:][::-1], new_s[head:][::-1]]))
    offsets = list(range(head)) + [-1] * (len(new_s) - head - tail) + list(range(len(old_s) - tail, len(old_s)))
    old_lines, new_lines = old_s.splitlines(True), new_s.splitlines(True)
    pairs = len(old_lines) * len(new_lines)
    if diff_budget[1] is None:
        diff_budget[1] = time.monotonic() + 1.5
    if pairs > diff_budget[0] or time.monotonic() > diff_budget[1]:
        return offsets                    # too big to diff quickly: only the shared start and end are kept
    diff_budget[0] -= pairs
    offsets = [-1] * len(new_s)
    old_at = [0]
    for line in old_lines:
        old_at.append(old_at[-1] + len(line))
    new_at = [0]
    for line in new_lines:
        new_at.append(new_at[-1] + len(line))
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                offsets[new_at[j]:new_at[j + 1]] = range(old_at[i], old_at[i + 1])
    return offsets


class NoFit(Exception):
    """A multi-edit Claude Code itself refuses: the tool call fails and nothing is written."""


# Claude Code (2.1) matches old_string as written, else with curly quotes made straight (taking
# the text of the file there), else with \uXXXX escapes read as characters, else with characters
# written as such escapes. It then gives new_string the quote style or the escapes of what it
# matched. The guard does the same, so that it scans what lands on disk.
SQ, DQ = chr(39), chr(34)
CURLY = ((chr(0x2018), SQ), (chr(0x2019), SQ), (chr(0x201C), DQ), (chr(0x201D), DQ))
QUOTE_CHARS = set(SQ + DQ + "".join(c for c, _ in CURLY))
ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")
OPENERS = (" ", "\t", "\n", "\r", "(", "[", "{", chr(0x2014), chr(0x2013))


def fold(s):
    for c, q in CURLY:
        s = s.replace(c, q)
    return s


def units(s):
    """The UTF-16 code units of s, as Claude Code (JavaScript) sees the string."""
    return array.array("H", s.encode("utf-16-le", "surrogatepass"))


def unescape(s):
    s = re.sub(r"(\\\\)|\\u([0-9a-fA-F]{4})", lambda m: m.group(0) if m.group(1) else chr(int(m.group(2), 16)), s)
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def escaped_pattern(s):
    """A pattern for s with each non-ASCII code unit written as a \\uXXXX escape of either case."""
    out = []
    for u in units(s):
        if u >= 128:
            out.append(r"\\u" + "".join("[%s%s]" % (h, h.upper()) if h >= "a" else h for h in "%04x" % u))
        else:
            out.append(re.escape(chr(u)))
    return "".join(out)


def actual(text, old):
    """The text of the file Claude Code replaces for old, or None when it finds none."""
    if old in text:
        return old
    if QUOTE_CHARS.intersection(old):         # without a quote character folding finds nothing new
        at = fold(text).find(fold(old))
        if at >= 0:
            return text[at:at + len(old)]
    if ESCAPE.search(old):
        plain = unescape(old)
        if plain != old and plain in text:
            return plain
    if not old.isascii():
        m = re.search(escaped_pattern(old), text)
        if m:
            return m.group(0)
    return None


def opens(chars, k):
    return k == 0 or chars[k - 1] in OPENERS


def restyle(old, act, new):
    """new_string as Claude Code writes it once old matched act in the file."""
    if old == act:
        return new
    if chr(0x201C) in act or chr(0x201D) in act:
        new = "".join((chr(0x201C) if opens(new, k) else chr(0x201D)) if c == DQ else c for k, c in enumerate(new))
    if chr(0x2018) in act or chr(0x2019) in act:
        def single(k):
            if 0 < k < len(new) - 1 and new[k - 1].isalpha() and new[k + 1].isalpha():
                return chr(0x2019)
            return chr(0x2018) if opens(new, k) else chr(0x2019)
        new = "".join(single(k) if c == SQ else c for k, c in enumerate(new))
    if not old.isascii() and re.fullmatch(escaped_pattern(old), act):
        # The file spells these characters as escapes: so does the new text, in the same case.
        spelled, low, up, v = {}, 0, 0, 0
        for u in units(old):
            if u >= 128:
                spelled[u] = act[v + 2:v + 6]
                low += sum(1 for d in spelled[u] if "a" <= d <= "f")
                up += sum(1 for d in spelled[u] if "A" <= d <= "F")
                v += 6
            else:
                v += 1
        return "".join("\\u" + spelled.get(u, ("%04X" if up > low else "%04x") % u) if u >= 128 else chr(u)
                       for u in units(new))
    if ESCAPE.search(old) and unescape(old) == act:
        return unescape(new)
    return new


def target_of(text, act, new):
    """What Claude Code replaces: a deletion takes the line break after the old text with it."""
    return act + "\n" if new == "" and not act.endswith("\n") and act + "\n" in text else act


def place(before, edits):
    """Apply the edits to the text on disk: (text after, changed spans, first changed line,
    unchanged line -> old line, new characters, whether lines end at lone CRs and, if they do,
    where each character came from)."""
    after, origin, fresh = before, array.array("l", range(len(before))), set()
    for e in edits:
        old_s, new_s = e.get("old_string"), e.get("new_string")
        if not isinstance(old_s, str) or not isinstance(new_s, str):
            raise ValueError
        if old_s == "":
            after, origin = new_s, array.array("l", [-1]) * len(new_s)   # Claude Code writes the new text alone
            fresh.update(new_s)
            continue
        act = actual(after, old_s)
        if act is None:
            # An old_string with markup in it may be rewritten before it is matched, so it is
            # never taken as refused.
            if MULTI and "<" not in old_s:
                raise NoFit
            raise ValueError
        if MULTI and not e.get("replace_all") and after.find(act, after.find(act) + len(act)) >= 0:
            raise NoFit                   # there more than once
        new_s = restyle(old_s, act, new_s)
        old_s = target_of(after, act, new_s)
        found, at = [], after.find(old_s)
        while at >= 0:
            found.append(at)
            if not e.get("replace_all"):
                break
            at = after.find(old_s, at + len(old_s))
        # Lines the edit repeats unchanged (context around and between its changes) keep their
        # origin: only the lines that differ are new. Past a few thousand lines, only the shared
        # start and end are matched, to stay quick.
        offsets = new_offsets(old_s, new_s)
        if found:
            fresh.update(new_s[k] for k, o in enumerate(offsets) if o < 0)
        text_parts, origin_parts, last = [], [], 0
        for at in found:
            text_parts += [after[last:at], new_s]
            origin_parts += [origin[last:at],
                             array.array("l", [origin[at + k] if k >= 0 else -1 for k in offsets])]
            last = at + len(old_s)
        text_parts.append(after[last:])
        origin_parts.append(origin[last:])
        after = "".join(text_parts)
        origin = array.array("l")
        for part in origin_parts:
            origin.extend(part)
    # Text with lone CRs and no newline (old Mac line endings) is split by the scanner at each CR
    # in prose and Python: lines are numbered that way here too. The same characters stand at
    # the same offsets, so only the line breaks differ.
    lone_cr = all("\n" not in t and "\r" in t for t in (before, after))
    old_text, new_text = (before.replace("\r", "\n"), after.replace("\r", "\n")) if lone_cr else (before, after)
    old_starts = [0] + [m.end() for m in re.finditer("\n", old_text)]
    spans, moved, first, line_no, start = [], {}, None, 1, 0
    while start <= len(new_text):
        stop = new_text.find("\n", start)
        stop = len(new_text) if stop < 0 else stop
        last_char = min(stop, len(new_text) - 1)          # the line with its newline
        run = origin[start:last_char + 1]
        # Unchanged: one run of old characters that starts and ends where an old line did (a line
        # that now begins half way through an old one has changed).
        kept = len(run) == 0 or (-1 not in run and run[-1] - run[0] == len(run) - 1
                                 and old_starts[bisect.bisect_right(old_starts, run[0]) - 1] == run[0]
                                 and (run[-1] == len(old_text) - 1 or old_text[run[-1]] == "\n" or stop == len(new_text)))
        if kept and len(run):
            moved[line_no] = bisect.bisect_right(old_starts, run[0])
            if first is None and (run[0] != 0 if not start else
                                  origin[start - 1] >= 0 and run[0] - origin[start - 1] != 1):
                first = line_no                           # lines were deleted just above (or at the top)
        elif not kept:
            spans.append((line_no, line_no))
            first = line_no if first is None else first
        line_no += 1
        start = stop + 1
    if first is None and before != after:
        first = line_no - 1                               # only the end of the file was cut
    # Mixed: one side has lone CRs and the other newlines; the line numbers do not line up.
    if not lone_cr and any("\n" not in t and "\r" in t for t in (before, after)):
        spans = [(1, after.count("\r") + after.count("\n") + 1)]
        first, moved = 1, {}
    return after, spans, first, moved, fresh, lone_cr, origin if lone_cr else None


LATE = "late"
NOFIT = "nofit"


def place_in_time(before, edits):
    """place() in a child process the guard can stop: a search for a long old_string in a long,
    repetitive file runs inside one C call that no signal interrupts. None when it cannot be
    placed (the new text is then scanned on its own); LATE when it does not finish in time or the
    child cannot be started or answer, which blocks as not checked."""
    try:
        read_end, write_end = os.pipe()
        pid = os.fork()
    except OSError:
        return LATE                       # no pipe or no process: the edit cannot be checked
    if pid == 0:
        os.close(read_end)
        try:
            data = pickle.dumps(place(before, edits))
        except ValueError:
            data = pickle.dumps("error")      # an edit that does not fit the file
        except NoFit:
            data = pickle.dumps(NOFIT)
        except BaseException:
            data = b""                        # anything else: not checked
        with os.fdopen(write_end, "wb") as fh:
            fh.write(data)
        os._exit(0)
    os.close(write_end)
    chunks, deadline = [], STARTED + BUDGET - SCAN_RESERVE
    with os.fdopen(read_end, "rb") as fh:
        while True:
            left = deadline - time.monotonic()
            ready = select.select([fh], [], [], max(0, left))[0] if left > 0 else []
            if not ready:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
                return LATE
            chunk = os.read(fh.fileno(), 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
    status = os.waitpid(pid, 0)[1]
    data = b"".join(chunks)
    if status != 0 or not data:
        return LATE                       # the child crashed or was killed: not checked
    try:
        result = pickle.loads(data)
    except Exception:
        return LATE                       # the child died half way through its answer
    return result if result != "error" else None


def read_text(p):
    """The file as Claude Code reads it: UTF-16 by its byte order mark, else UTF-8 with invalid
    bytes replaced, and CRLF line ends read as LF (Claude Code matches old_string there and writes
    the line ends back). A lone CR stays a CR, as the scanner sees it. None when the text is
    larger than the scanner reads."""
    with open(p, "rb") as fh:
        raw = fh.read(4 * MAX_SCAN_BYTES + 1)
    if len(raw) > 4 * MAX_SCAN_BYTES:
        return None
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw[2:].decode("utf-16-le" if raw[:1] == b"\xff" else "utf-16-be", "replace")
    else:
        text = raw.decode("utf-8", "replace")
    if len(text.encode("utf-8")) > MAX_SCAN_BYTES:
        return None
    return text.replace("\r\n", "\n")


def only_adds(edits):
    """True when every edit keeps its old text whole inside its new text (its new text is
    still scanned on its own)."""
    return all(isinstance(e.get("old_string"), str) and e["old_string"] and isinstance(e.get("new_string"), str)
               and e["old_string"] in e["new_string"] for e in edits)


# A symlinked file is judged as the regular file it points to (dotfiles are often links).
real = os.path.realpath(path) if path else path
# Why the write is blocked as not checked, if it is; unplaced: the new texts are scanned too.
late, unplaced = "", False
IN_TIME = "the edit could not be placed in the file in time"
if not whole and edits and edits[0].get("old_string") == "" and isinstance(edits[0].get("new_string"), str):
    try:
        empty = not os.path.exists(real) or (os.path.isfile(real) and os.path.getsize(real) == 0)
    except OSError:
        empty = False
    if empty:
        # It creates the file (a multi-edit may go on editing what the first edit wrote): build
        # the result, in the child the guard can stop, and judge it as a write. When Claude Code
        # refuses a later edit (or may rewrite its markup first), the first text is judged as a
        # write and every new text on its own: a refused edit writes nothing, so that costs nothing.
        made = place_in_time("", edits)
        if made == LATE:
            late = IN_TIME
        elif made is None or made == NOFIT:
            whole, body, unplaced = [edits[0]["new_string"]], edits[0]["new_string"], True
        else:
            whole, body = [made[0]], made[0]
if not whole and edits and not late:
    try:
        if os.path.isfile(real):
            before = read_text(real)
            in_place = place_in_time(before, edits) if before is not None else "large"
    except (OSError, ValueError):
        in_place = LATE if sys.exc_info()[0] is BlockingIOError else None
    if isinstance(in_place, tuple) and len(in_place[0].encode("utf-8", "surrogatepass")) > MAX_SCAN_BYTES:
        in_place = "large"
    if in_place == LATE:
        in_place, late = None, IN_TIME
    elif in_place == "large":
        # Too large to place: an edit that only adds text is judged on its new text, any other blocks.
        in_place, late = None, ("" if only_adds(edits) else "the file is too large to check this edit in place")
    elif in_place == NOFIT:
        in_place = None                   # Claude Code refuses it: its new text is scanned on its own

# Never police the hygiene tooling itself or the forensics reference material: both quote the
# characters scanned for. The tooling is matched by file name, the reference files by their
# folder. A path with ".." or "." segments gets no exemption, since it can name any file. The
# tooling is exempt only where it is installed: a file of that name elsewhere is checked.
segments = path.split("/")
TOOL_HOMES = tuple(os.path.realpath(d) + "/" for d in (
    os.environ.get("AI_RULES_HOME") or os.path.expanduser("~/.ai-rules"), os.path.expanduser("~/.claude/hooks")))


def exempt(p):
    parts = p.split("/")
    if ".." in parts or "." in parts:
        return False
    return "/skills/ai-content-forensics/reference/forensics-" in p or "/.trash-preview/" in p \
        or (parts[-1] in ("content-hygiene", "pre-write-guard.sh", "post-write-audit.sh")
            and os.path.realpath(p).startswith(TOOL_HOMES))


# A symlink is exempt only when what it points to is too: a link named content-hygiene does not
# excuse whatever file it leads to.
if exempt(path) and (not real or real == path or exempt(real)):
    sys.exit(0)

# The opt-out marker counts when it is in the file: in the text of a whole-file write, or in
# the first 30 lines of the file on disk for an edit. A marker inside the new text of an edit
# does not excuse that text, and an edit that takes the marker out of the first 30 lines (as
# the scanner counts them) is judged.


def marker_kept(head):
    """For an edit that could not be placed: True when no old_string, read any way Claude Code
    may match it, reaches into the marker, and the marker stays in the first 30 lines even if
    every line the edits add lands above it."""
    for e in edits:
        old_s = e.get("old_string") if isinstance(e.get("old_string"), str) else ""
        for view in (old_s, fold(old_s), unescape(old_s)):
            if MARKER in view or any(view.endswith(MARKER[:k]) or view.startswith(MARKER[-k:])
                                     for k in range(3, len(MARKER))):
                return False
    breaks, added = re.compile("\r\n|\r|\n"), 0
    for e in edits:
        old_s, new_s = e.get("old_string"), e.get("new_string")
        if isinstance(old_s, str) and isinstance(new_s, str):
            added += max(0, len(breaks.findall(new_s)) - len(breaks.findall(old_s)))
    at = next(k for k, line in enumerate(head) if MARKER in line)
    return at + added < 30


flags = []
if not whole:
    flags = ["--no-marker", "--fragment"]
    try:
        if not late and os.path.isfile(real):
            with open(real, encoding="utf-8", errors="replace", newline="") as fh:
                head = re.split("\r\n|\r|\n", fh.read(1 << 16), 30)[:30]
            if any(MARKER in line for line in head) \
                    and (MARKER in "\n".join(re.split("\r\n|\r|\n", in_place[0], 30)[:30]) if in_place is not None
                         else marker_kept(head)):
                sys.exit(0)
    except OSError:
        pass

name = segments[-1] or "stdin.txt"
# A symlink, or a file under a symlinked folder, is judged by what it points to: notes.md ->
# app.py is Python, and wf/ci.yml under wf -> .github/workflows is a workflow.
judged = real if real and real != path else path
scan_name = "".join(c if c.isprintable() and c not in ":" else "_" for c in (judged or name))
# A notebook cell is Python unless it is Markdown; the .ipynb file as a whole is data. An
# edit that leaves out cell_type keeps the type of the cell it replaces, read from the file;
# a cell that cannot be found there is taken as code.
cell_type = tool_input.get("cell_type")
if tool_input.get("notebook_path") and not whole and cell_type is None:
    try:
        if os.path.isfile(real) and os.path.getsize(real) <= 2000000:
            with open(real, encoding="utf-8") as fh:
                cells = json.load(fh).get("cells") or []
            cell_type = next((c.get("cell_type") for c in cells
                              if isinstance(c, dict) and c.get("id") == tool_input.get("cell_id")), None)
    except Exception:                     # unreadable or too deeply nested: judged as code below
        cell_type = None
if tool_input.get("notebook_path") and not whole and cell_type != "markdown":
    path = path + ".py"
    name = name + ".py"
    scan_name = scan_name + ".py"


def scan(text, flags):
    """The scanner rows for text; a run that does not finish is a not-checked row. Each run has
    the time the guard has left, short of its budget."""
    left = BUDGET - 1 - (time.monotonic() - STARTED)
    if left < 1.5:
        return ["HARD  %s:1:1  not-checked  the text could not be scanned in time" % scan_name]
    try:
        # Claude Code writes a lone surrogate as U+FFFD: the scanner sees what lands on disk, and
        # its input stays UTF-8 (bytes that are not would send it to a legacy codec).
        run = subprocess.run([sys.executable, "-I", os.environ["HYGIENE"], "--stdin", "--name=" + scan_name, "--quiet",
                              "--deadline", "%.1f" % (left - 1)] + flags,
                             input=re.sub("[\ud800-\udfff]", "\ufffd", text).encode("utf-8"),
                             capture_output=True, timeout=left - 0.5)
    except subprocess.TimeoutExpired:
        return ["HARD  %s:1:1  not-checked  the text could not be scanned in time" % scan_name]
    except OSError as e:
        if e.errno in (errno.ENOENT, errno.EACCES):
            sys.exit(0)                   # no scanner installed: the guard fails open, as documented
        return ["HARD  %s:1:1  not-checked  the scanner could not be started (%s)" % (scan_name, e.strerror)]
    rows = run.stdout.decode("utf-8", "replace").splitlines()
    if run.returncode not in (0, 1):
        # The scanner did not finish normally (whatever the content did to it): not checked.
        rows.append("HARD  %s:1:1  not-checked  the scanner stopped with exit %d" % (scan_name, run.returncode))
    return rows


prefix = "%s:" % scan_name


def parse(row):
    """(line, column, rule, message) of a HARD row, read after the exact file name; None otherwise."""
    rest = row[len("HARD"):].lstrip() if row.startswith("HARD") else ""
    if not rest.startswith(prefix):
        return None
    fields = rest[len(prefix):].split(None, 2)
    where = fields[0].split(":") if fields else []
    if len(fields) < 2 or len(where) != 2 or not all(w.isdigit() for w in where):
        return None
    return int(where[0]), int(where[1]), fields[1], fields[2] if len(fields) > 2 else ""


if late:
    lines = ["HARD  %s:1:1  not-checked  %s" % (scan_name, late)]
elif in_place is None:
    # The new text on its own. A row that cannot be read is kept: it blocks rather than slipping through.
    lines = [row for row in scan(body, flags) if row.startswith("HARD")]
    if unplaced:
        lines += [row for row in scan("\n".join(parts), ["--no-marker", "--fragment"]) if row.startswith("HARD")]
else:
    # The file is scanned before and after the edit. A finding counts when it is on a changed
    # line or was not there before (the edit can turn text into code further down), so an old
    # finding elsewhere is not charged to the edit, and a finding that depends on the
    # characters around it is judged with them.
    after, spans, first, moved, new_chars, lone_cr, origin = in_place
    no_cap = []

    def lifts_cap():
        """True when the scanner takes --no-cap (asked once): a scan past the cap is then one run."""
        if not no_cap:
            try:
                run = subprocess.run([sys.executable, "-I", os.environ["HYGIENE"], "--help"],
                                     capture_output=True, timeout=3)
                no_cap.append(run.returncode == 0 and b"--no-cap" in run.stdout)
            except (OSError, subprocess.TimeoutExpired):
                no_cap.append(False)
        return no_cap[0]

    # A large file is scanned whole on both sides without the cap when the scanner allows it: one
    # round, where a capped list would take a rescan of the tail and of the old file after it.
    # A small file is quick to rescan, so it is not worth asking the scanner first.
    lift = ["--no-cap"] if len(before) >= 100000 and lifts_cap() else []
    both = {}
    tasks = [("old", before, ["--no-marker"] + lift), ("new", after, ["--no-marker"] + lift)]
    tail_ranges = [(1 if lone_cr else first, after.count("\n") + after.count("\r") + 1)] if first is not None else []
    workers = [threading.Thread(target=lambda k, t, f: both.__setitem__(k, scan(t, f)), args=task)
               for task in tasks]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    old_rows, new_rows = both["old"], both["new"]
    seen = set()
    for row in old_rows:
        found = parse(row)
        if found:
            seen.add(found)
    lines = [row for row in old_rows if (parse(row) or (0, 0, "", ""))[2] == "not-checked"]
    placed = [(row, parse(row)) for row in new_rows if row.startswith("HARD")]
    lines += [row for row, found in placed if found is None]
    placed = [(row, found) for row, found in placed if found is not None]
    # Findings about the file as a whole (so many private-use characters, joiners or selectors)
    # are reported at 1:1 with a count; one the file had before, with only the count changed,
    # is not charged to the edit.
    def norm(msg):
        return re.sub(r"[0-9]+", "#", msg)

    def count(msg):
        n = re.match(r"[0-9]+", msg)
        return int(n.group(0)) if n else 0

    # Only rows about the whole file.
    # The count may not grow at all through new characters of its kind: across several edits a
    # few at a time would add up to a carrier. Each kind is the set the scanner counts, with the
    # count at which it reports the file (PUA_HARD_FILE and IVS_HARD_FILE in the scanner; the
    # joiners depend on the letters around them, so only the row of the scanner tells).
    kinds = {"private-use": ("[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]", 8),
             "hidden-selectors": ("[\ufe00-\ufe0d\U000e0100-\U000e01ef\u180b-\u180d\u180f\u115f\u1160]", 16),
             "invisible-char": ("[\u200c-\u200f\u061c]", None)}

    def subsequence(short, full):
        it = iter(full)
        return all(c in it for c in short)

    def adds_kind(rule):
        """True when the edit may have rewritten the carrier a whole-file row counts: it brings
        in a character of that kind, or the characters of that kind no longer read in the order
        they had, with some left out at most. Lines that trade places rewrite it."""
        if rule not in kinds:
            return True
        kind = kinds[rule][0]
        if re.search(kind, "".join(new_chars)):
            return True
        return not subsequence(re.findall(kind, after), re.findall(kind, before))

    def is_whole(f):
        return f[:2] == (1, 1) and f[2] != "too-many" and ("in this file" in f[3] or "letters that use them" in f[3])

    whole_file = {(f[2], norm(f[3])): count(f[3]) for f in seen if is_whole(f)}

    def capped(rows):
        return any((parse(r) or (0, 0, ""))[2] == "too-many" for r in rows)

    def spec(ranges):
        """A --lines value for these (low, high) ranges; past 100000 characters (a command line
        has limits) nearby ranges are merged, which only reports more lines."""
        gap = 1
        while True:
            merged = []
            for lo, hi in ranges:
                if merged and lo - merged[-1][1] <= gap:
                    merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
                else:
                    merged.append((lo, hi))
            text = ",".join("%d" % lo if lo == hi else "%d-%d" % (lo, hi) for lo, hi in merged)
            if len(text) <= 100000:
                return text
            gap *= 4

    def scan_lines(text, ranges):
        """(findings, rows that block) on these lines of text: in one run when the scanner can lift
        its cap, else read past the cap by scanning on from the last line it listed; None when that
        cannot finish in time."""
        found, extra = set(), []
        lift = ["--no-cap"] if lifts_cap() else []
        initial = scan(text, ["--no-marker", "--lines", spec(ranges)] + lift) if lift else None
        while ranges:
            if initial is None and time.monotonic() - STARTED > 5.5:
                return None               # one more scan could outlast the hook
            rows = initial if initial is not None else scan(text, ["--no-marker", "--lines", spec(ranges)] + lift)
            initial = None
            rows = [r for r in rows if r.startswith("HARD")]
            extra += [r for r in rows if (parse(r) or (0, 0, "not-checked"))[2] == "not-checked"]
            got = []
            for r in rows:
                f = parse(r)
                if f and f[2] not in ("too-many", "not-checked"):
                    got.append(f)
                    row_of.setdefault(f, r)
            found.update(got)
            if not capped(rows):
                return found, extra
            # The cap keeps the first findings in line order: lines before the last one listed
            # are complete, and that line may not be.
            nxt = max([f[0] for f in got] or [0])
            if nxt <= ranges[0][0]:
                return None
            ranges = [(max(lo, nxt), hi) for lo, hi in ranges if hi >= nxt]
        return found, extra

    def not_checked(what):
        return "HARD  %s:1:1  not-checked  %s could not be scanned in time" % (scan_name, what)

    def pua_row_hard():
        """True when the scanner reports a file of this name and kind for private-use characters
        spread through it (in code and terminal configs it only warns): asked with a sample."""
        head = after.split("\n", 1)[0] + "\n" if after.startswith("#!") else ""
        rows = scan(head + "".join("a" + chr(0xE000 + k) for k in range(8)) + "\n", ["--no-marker"])
        return any((parse(r) or (0, 0, "not-checked", ""))[2] in ("private-use", "not-checked")
                   for r in rows if r.startswith("HARD"))

    # The scanner reports at most so many findings, in file order. When the new file is over the
    # cap, it is scanned again from the first changed line (lines deleted there count as a
    # change) to the end, a part at a time, so a finding the edit causes further down, on a line
    # it kept, is seen. Lines above the first change read the same as before.
    row_of = {f: r for r, f in placed}
    new = [f for _, f in placed if f[2] != "too-many"]
    if capped(new_rows) and first is not None:
        got = scan_lines(after, tail_ranges)
        if got is None:
            lines.append(not_checked("the rest of the file"))
        else:
            new = list(set(new) | got[0])
            lines += got[1]
    old_capped = capped(old_rows)
    old_last = max([f[0] for f in seen if f[2] != "too-many"] or [0])
    changed = {k for lo, hi in spans for k in range(lo, hi + 1)}
    first_line = len(after.replace("\r", "\n").split("\n", 1)[0])
    pending = []
    for line_no, col, rule, msg in sorted(new):
        f = (line_no, col, rule, msg)
        row = row_of[f]
        if rule == "not-checked":
            lines.append(row)
        elif is_whole(f):
            # Decided by the count and the characters the edit adds, never by where it stands.
            if (rule, norm(msg)) not in whole_file or count(msg) > whole_file[(rule, norm(msg))] or adds_kind(rule):
                lines.append(row)
        elif lone_cr and line_no == 1 and col >= first_line + 1:
            # The scanner kept the file as one line (a shell file): past the first CR the column
            # is read back to where that character stood before.
            was = origin[col - 1] if col - 1 < len(origin) else -1
            if was < 0 or (1, was + 1, rule, msg) not in seen:
                lines.append(row)
        elif line_no in changed or line_no not in moved:
            lines.append(row)
        elif (moved[line_no], col, rule, msg) in seen:
            continue
        elif old_capped and moved[line_no] > old_last:
            pending.append((row, (moved[line_no], col, rule, msg)))
        else:
            lines.append(row)
    for rule, (kind, least) in kinds.items():
        # A whole-file row the scanner left out (it does for private-use characters when a run of
        # them is already reported on a line) still counts when the edit adds to the carrier.
        if least is None or any(is_whole(f) and f[2] == rule for f in new):
            continue
        total = len(re.findall(kind, after))
        if total >= least and adds_kind(rule) and (rule != "private-use" or pua_row_hard()):
            lines.append("HARD  %s:1:1  %s  %d characters of this kind in this file (enough to carry hidden data)"
                         % (scan_name, rule, total))
    if pending:
        # Kept lines past the end of the old list: their old findings are read the same way.
        olds = sorted({o[0] for _, o in pending})
        got = scan_lines(before, [(k, k) for k in olds])
        if got is None:
            lines.append(not_checked("the file before the edit"))
        else:
            lines += got[1]
            lines += [row for row, o in pending if o not in got[0]]
report = "\n".join(lines)
if not report:
    sys.exit(0)

sys.stderr.write("""Blocked: content-hygiene violations in %s.

%s

Fix and retry:
  - Invisible or non-ASCII characters: replace with plain ASCII.
    Straight quotes, a hyphen for an em dash, three periods for the ellipsis character.
  - Placeholders and elided code: write the actual implementation.
    Never ship a comment that stands in for code.
  - Scaffolding: deliver the artifact, not the conversation around it.

If a character is genuinely required (test fixture, reference material),
put the marker  hygiene:ignore-file  in the first 30 lines of the file.
""" % ("".join(c if c.isprintable() else "?" for c in path) if path else "this content", report))
sys.exit(2)
'
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  echo "Blocked: the write guard failed (exit $rc), so this write was not checked (not-checked)." >&2
  exit 2
fi
exit "$rc"
