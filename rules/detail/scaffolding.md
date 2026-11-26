# No scaffolding in output: detail
<!-- hygiene:ignore-file - quotes the patterns it documents -->

Loaded on demand from the core rules (~/.ai-rules/RULES.md).

Nothing from the generation process reaches the deliverable.

**Never emit:**

- Preamble: "Certainly!" · "Sure! Here's a…" · "Great question!" · "Of course!"
- Trailing offers: "Let me know if you'd like me to…" · "I hope this helps!" · "Would you like me to expand on any section?"
- Self-reference: "Here's the draft you requested" · "As an AI language model" · "As of my last knowledge update"
- Unfilled placeholders: `[Your Name]` · `[Insert Company]` · `[Date]` · `[XX]`
- Citation objects, `<think>` blocks, tool-call tags, or any internal markup
- LaTeX delimiters `\( \)` `\[ \]` in non-mathematical prose
- Raw markdown (`**bold**`, `###`, `---`) in a context that won't render it: email bodies, form fields, plain-text files, commit messages

**Deliver the artifact, not the conversation around it.**
