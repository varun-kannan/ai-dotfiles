---
name: ai-content-forensics
description: Determine whether text, code, images, audio, video, documents, or datasets were AI-generated or AI-assisted, and interpret detection results correctly. Use when asked to check if something was written by AI, verify content provenance, evaluate an AI-detector score, check C2PA or watermark status, investigate suspected AI-generated code or citations, respond to an AI-use accusation, or design an AI-detection policy. Also use when producing content that must be verifiable — checking that dependencies, citations, and sources actually resolve.
---

# AI Content Forensics

Evidence-graded methods for establishing content provenance. Two reference files hold the detail; this file is the routing layer and the non-negotiable principles.

> **Verification status.** Claude's text watermark, its 2 August 2026 start
> date, the transition period for earlier models, and the gated detection API
> were confirmed against Anthropic's own documentation on 2026-09-11. Claims
> marked **[U]** in the reference files are unverified and must not be presented
> as settled. Watermark coverage is per model version and goes stale; re-check
> before relying on the model list below.

## Start here — evidence tiers

| Tier | Class | Establishes | Public tooling |
|---|---|---|---|
| **E1** | Cryptographic provenance (C2PA, signed attestation) | Strong | ✅ Free |
| **E2** | Provider watermark | Strong | ⚠️ Images/audio yes; Claude text **no** |
| **E3** | Audit trail (version history, git log, agent logs) | Strong | ✅ Free |
| **E4** | Verifiable content checks (phantom imports, dead DOIs, scaffolding) | Strong | ✅ Free |
| **E5** | Detectors and stylometry | **Weak alone** | ⚠️ Unreliable |

**Work top-down. Stop at the first tier that resolves it.** Most people jump to E5 and skip E4, which is free, deterministic, and often decisive.

## Principles that override any detector output

1. **A detected watermark proves involvement, not authorship** — it cannot separate "wrote" from "edited" from "translated." It can also be **spoofed** onto human text.
2. **No watermark proves nothing.** Wrong model version, different vendor, open weights, paraphrased, too short, or metadata stripped.
3. **Watermark coverage is per-model-version, not per-vendor.** Claude marks only models launched on/after 2 Aug 2026 — currently Fable 5.1 and Mythos 5.1. Opus 5, Sonnet 5, Haiku 4.5 are **not** marked.
4. **Base rates decide everything.** A 1% FPR gives ~99% positive predictive value at 50% prevalence and ~32% at 0.5%. Compute PPV before acting on any score. See `forensics-core.md` §5.
5. **Never accuse on style alone.** Every stylistic signal dies to one instruction or one paraphrase pass.
6. **Absence of evidence is not evidence of absence.** Never state a tool or source doesn't exist based on a search you didn't run.
7. **Ask them to explain and modify it.** Stronger than any tool score, and it survives appeal.

## Quick checks

```bash
# E1 — file provenance
c2patool file.png
exiftool -DigitalSourceType -Software -Description file.jpg
# Free verifiers: openai.com/research/verify/ (images+audio) · claude.com/check-files

# E4 — invisible characters (the locale prefix is REQUIRED)
LC_ALL=C.UTF-8 grep -nP '[\x{00A0}\x{00AD}\x{200B}-\x{200F}\x{2028}\x{202F}\x{2060}\x{FEFF}]' file

# E4 — phantom dependencies (strongest code signal)
npm view <pkg> version ; pip index versions <pkg> ; cargo search <crate>

# E3 — repository trail
git log --all --numstat --format='%h %ad %an %s' --date=iso
```

## Routing — read the reference files, don't answer from this page alone

The two files below live in the `reference/` directory **next to this SKILL.md**. Resolve them relative to this skill's own directory (typically `~/.claude/skills/ai-content-forensics/reference/`).

**Read the relevant file before answering** whenever the question goes beyond the tier table and principles above. This page is a routing layer, not a substitute for the detail — answering a substantive provenance question from this summary alone will produce confident, under-specified answers.

**`reference/forensics-core.md`** — read when the question involves:

| Topic | Section |
|---|---|
| Watermark mechanism, entropy limits, attacks, spoofing | §4 |
| **Base rates, PPV, false-positive arithmetic** | §5 |
| Hybrid human/AI text | §6 |
| Code provenance, phantom dependencies, git trailers | §7 |
| Detectors, Turnitin's 20% threshold, non-native-speaker bias | §8 |
| Chain of custody, hashing, tool versioning | §9 |
| **Responding to an AI-use accusation** | §10 |
| Institutional policy design | §11 |
| Worked example and report template | §12–13 |

**`reference/forensics-modalities.md`** — read when the question involves:

| Topic | Section |
|---|---|
| Documents, PDF `Producer`, DOCX `core.xml` | §17 |
| Generator-specific image metadata (Midjourney, SD, DALL·E) | §18 |
| Video | §19 |
| Audio, voice cloning, music | §20 |
| Fabricated datasets, Benford's Law, survey fraud | §21 |
| Academic paper mills, tortured phrases | §22 |
| **Measured detector false-positive rates (RAID)** | §23.1 |
| Humaniser and paraphraser evasion tells | §24 |
| Model-specific style habits | §25 |
| **Legal and privacy exposure of running detection** | §26 |
| Decision flow | §27 |
| Costs, rate limits, timings | §28 |

Read only the sections needed — the two files total ~12,500 words. If a question spans both, read both.

**Two checks that must come from the reference files, never from memory:** the base-rate arithmetic in core §5 and the measured FPR table in modalities §23.1. Both produce wrong answers when approximated.

## Reporting standard

Never output "N% AI generated." Report by tier, state limitations, and record what was **not** checked. Template in `forensics-core.md` §13.

Say **"confirmed AI-processed"** only with provider-linked evidence. Otherwise: **"shows indicators consistent with AI-assisted work."**

## Boundaries

Do not use this to build a detector-evasion playbook. Paraphrasers and injected typos leave a worse, more incriminating signature than what they mask — that mechanism is what produced the tortured phrases now driving thousands of paper retractions.

Where a disclosure obligation exists, disclose. Detection findings about a specific person carry real consequences; corroborate across tiers, and never act on E5 alone.
