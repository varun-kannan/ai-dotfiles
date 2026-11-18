# Scope of the rules: detail
<!-- hygiene:ignore-file - quotes the patterns it documents -->

Loaded on demand from the core rules (~/.ai-rules/RULES.md).

Two limits, stated plainly so nothing here is relied on that isn't true.

**These rules do not defeat watermarking.** Anthropic's statistical text watermark has no opt-out and cannot be disabled by instruction. It is also largely irrelevant here: it lives in free word choices, so code carries almost none of it, and models released before 2 August 2026 carry none at all. **Never claim to have "removed a watermark."** Tools advertising Unicode-stripping as watermark removal are removing copy-paste artifacts, which are not watermarks.

**These are quality rules, not an evasion toolkit.** The distinction is practical, not just ethical:

- **Do not inject deliberate typos.** It degrades the work. Text with sophisticated vocabulary, perfect grammar, and three random transpositions is a stranger artifact than clean text.
- **Do not thesaurus-swap to avoid common words.** That produces the tortured-phrase failure — "capitalise on" for "use", "considerable" for "big" — which is more conspicuous than the original.
- **Do not artificially manipulate sentence-length variance.** Genuine variation comes from content. Injected variation produces a bimodal distribution that reads wrong.

Each of these is an *evasion* signal rather than a quality improvement, and evasion is generally treated more seriously than the underlying use.

**Where a disclosure obligation exists — academic policy, employer rules, publication terms, EU AI Act Article 50 for public-interest content — comply with it.** Clean output and honest disclosure are independent. These rules deliver the first and are not a substitute for the second.
