# Character hygiene: detail
<!-- hygiene:ignore-file - quotes the patterns it documents -->

Loaded on demand from the core rules (~/.ai-rules/RULES.md).

**Default to plain ASCII.** These characters break CSV imports, code diffs, regex matching, and terminal output — that alone justifies the rule.

**Never emit:**

| Codepoint | Name |
|---|---|
| `U+202F` | Narrow no-break space |
| `U+00A0` | Non-breaking space |
| `U+200B` `U+200C` `U+200D` | Zero-width space / non-joiner / joiner |
| `U+2060` | Word joiner |
| `U+FEFF` | Zero-width no-break space / BOM |
| `U+00AD` | Soft hyphen |
| `U+200E` `U+200F` | LTR / RTL marks |
| `U+2028` | Line separator |

**Prefer ASCII:**

- Straight quotes `"` `'`, not curly
- Three periods `...`, not `…`
- Hyphen `-` in ranges: `2020-2024`, not `2020–2024`
- **Em dashes: at most one per several paragraphs.** A comma, period, or parentheses usually works better. Never two in one sentence.
- Never mix straight and curly quotes in one document — that's a paste-splice artifact

**Check before delivering** anything long or destined for a file:

```bash
~/.ai-rules/bin/content-hygiene file    # installed with these rules; works everywhere
```

With GNU grep or ugrep only:

```bash
LC_ALL=C.UTF-8 grep -nP '[\x{00A0}\x{00AD}\x{200B}-\x{200F}\x{2028}\x{202F}\x{2060}\x{FEFF}]' file
```

Both halves of that grep fail silently: without the `LC_ALL=C.UTF-8` prefix GNU grep errors to stderr and prints nothing, and stock macOS `/usr/bin/grep` has no `-P` at all. Either way a pipeline reads the silence as "clean."
