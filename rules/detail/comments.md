# Comments and code hygiene: detail
<!-- hygiene:ignore-file - quotes the patterns it documents -->

Loaded on demand from the core rules (~/.ai-rules/RULES.md).

Comments explain **why**, never **what**.

```python
# BAD  — restates the code
counter += 1  # increment the counter

# GOOD — explains a decision
counter += 1  # retry budget; API rate-limits at 5/sec
```

Avoid, because they signal unreviewed generation and add nothing:

- A comment on every trivial function
- Uniform tutorial voice: "This function…", "Here we initialize…"
- Elaborate section banners in every small module
- Generic `TODO: add error handling` — a TODO must name a specific decision
- Identical docstring templates on functions of wildly different complexity
- Explaining language syntax (`if`, `try`, `map`, loops)
- Any leftover placeholder: `# your code here`, `// implement logic`

**Match the repo.** Quote style, indent, import ordering, and naming should be indistinguishable from surrounding files.
