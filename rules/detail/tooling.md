# Tooling: detail
<!-- hygiene:ignore-file - quotes the patterns it documents -->

Loaded on demand from the core rules (~/.ai-rules/RULES.md).

These checks are installed and enforced, not aspirational. Run them before
delivering anything written to a file.

```bash
~/.ai-rules/bin/content-hygiene FILE...    # sections 8, 11, 12
~/.ai-rules/bin/check-deps FILE...         # section 6, unresolved imports
```

These run automatically and do not need to be invoked:

- **PreToolUse on Write/Edit/NotebookEdit** blocks the write on a hard violation and returns
  the findings. If a write is blocked, fix the content; do not work around the
  check by writing through a shell heredoc.
- **PostToolUse on Write/Edit** reports imports missing from the manifest.
- **git pre-commit** blocks a commit carrying the same violations in staged
  files, whichever tool produced them.
- **git commit-msg** strips AI attribution trailers.

A file that must legitimately contain scanned characters (a test fixture, or
reference material quoting these patterns) opts out with the marker
`hygiene:ignore-file` in its first 30 lines. Use it sparingly and never to get
past a real finding.

For provenance questions, the `ai-content-forensics` skill carries the detail.
