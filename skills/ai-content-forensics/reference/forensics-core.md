# AI Content Forensics — v3
<!-- hygiene:ignore-file - quotes the patterns it documents -->

**Verified 8 September 2026.** Supersedes v1 and v2.

Read §0 first. It contains retractions of false accusations I made in v2 and a code bug that produced silent false negatives.

---

## 0. Corrections to v2

### 0.1 Retractions — I accused three sources of fabrication and was wrong all three times

In v2 I labelled the following as fabricated or unverifiable. I had not searched for any of them. I inferred absence from searches I never ran, then published the inference as a finding — the exact failure mode I was criticising in the same section.

| v2 claim | Reality |
|---|---|
| "`agentdiff` — could not verify it exists" | **Real.** `github.com/codeprakhar25/agentdiff`, also on crates.io (v0.1.27). Git-native, line-level, **ed25519-signed** attribution across Claude Code, Cursor, Copilot, Codex, Windsurf, OpenCode, Gemini. Records agent name, model, prompt excerpt, and exact line ranges to your own git refs. CLI-queryable, no server. Policy file at `.agentdiff/policy.toml` supports CI gates (`max_ai_percent`, `require_signed`). Your source described it accurately. |
| "`aiwatermarking.org` — could not verify" | **Real.** A tracker publishing `watermarks.json`, `watermarks.csv`, and `sources.json` under CC BY 4.0, with per-row source keys and explicit flagging of unverified rows. Its stated editorial policy — list what you cannot confirm as unconfirmed rather than omitting it — is better practice than what I did in v2. |
| "Zhang et al. — never verified, no URL" | **Real and peer-reviewed.** Zhang, Edelman, Francati, Venturi, Ateniese & Barak, *Watermarks in the Sand: Impossibility of Strong Watermarking for Language Models*, ICML 2024, PMLR 235:58851–58880. Code at `github.com/hlzhang109/impossibility-watermark`. **Important scope limit I should have stated:** their attack was demonstrated against KGW, EXP, and Unigram (green-list family) plus Stable Signature and Invisible Watermark for vision — **not against SynthID-Text**. |

Note also: **"agentdiff" is a colliding name.** At least four unrelated projects use it (line-level provenance; a Claude Code session tracker; an agent-behaviour CI tool; a trajectory-diff library). Specify the repo, not the name.

### 0.2 Code bug — the grep command failed silently

The v2 `grep -P` command does not run in a default POSIX/C locale:

```
grep: character code point value in \x{} or \o{} is too large
```

Error goes to stderr, exit code is non-zero, **no output**. In a pipeline this reads as "file is clean." A check whose failure mode is a silent false negative is worse than no check. Tested and corrected:

```bash
LC_ALL=C.UTF-8 grep -P '[\x{00A0}\x{00AD}\x{200B}-\x{200F}\x{2028}\x{202F}\x{2060}\x{FEFF}]' file.txt
```

The Python snippet was tested and works correctly (5/5 planted characters, correct Unicode names).

### 0.3 Other v2 defects corrected here

- **Stat laundering.** "~19% metadata detection coverage" came from the README of a hobby Rust CLI whose pull request was itself co-authored by Claude Haiku. Removed. Veracode and Stanford figures are now sourced to primary or dated appropriately.
- **Vendor conflict unflagged.** Several Pangram accuracy claims traced to Pangram's own blog summarising a study about Pangram. Now flagged inline.
- **Stale figure presented as current.** Veracode's 2025 report has been superseded by a July 2026 edition. Updated in §7.5.
- **Three competing taxonomies** (Layer 1–6 headers, Tier 1–5 in the report template, your source's 7 layers). Now one scheme, used consistently: **E1–E5**.
- **Uncalibrated scoring rubric presented as methodology.** Now explicitly labelled as an uncalibrated worksheet with a warning against disciplinary use.
- **No install instructions** for any recommended tool. Added in §3.3.

### 0.4 Source-quality grading used throughout

| Grade | Meaning |
|---|---|
| **[P]** | Primary — the organisation's own documentation, or the paper itself |
| **[S]** | Secondary — reporting or analysis of a primary source |
| **[V]** | Vendor claim about the vendor's own product; treat as marketing until independently replicated |
| **[U]** | Unverified — stated here, not confirmed |

---

## 1. Is the document you are reading watermarked?

v2 never answered this, which was the largest single gap.

**Almost certainly not.**

Anthropic watermarks models **launched on or after 2 August 2026**. Currently supported: **Fable 5.1 and Mythos 5.1**, both released 1 September 2026 — the first models to arrive after the cutoff. **[P]**

**Claude Opus 5 was released 24 July 2026** — nine days before the cutoff. **[S, multiple independent trackers]** It is not on the supported list. It sits in the retrofit queue, which under the EU's AI Omnibus transition runs to **2 December 2026**.

Consequences worth internalising:

- **The most-used Claude models today are not watermarked.** Opus 5, Sonnet 5, Haiku 4.5, the whole 4.x line — none of them, pending retrofit.
- Coverage is **per-model-version**, not per-vendor. "Claude watermarks its output" is false as a general statement, and will stay partially false at least until December.
- Anyone building a detection pipeline must treat marking support as **a versioned capability, not a provider-wide boolean.** The specific model ID serving a request determines whether a mark can exist at all.

---

## 2. Evidence tiers (E1–E5)

One taxonomy, used everywhere in this document.

| Tier | Class | What it establishes | Public tooling |
|---|---|---|---|
| **E1** | Cryptographic provenance | C2PA signed manifest; signed agent attestation | ✅ Yes, free |
| **E2** | Provider watermark | Keyed statistical mark | ⚠️ Images/audio yes; **Claude text no** |
| **E3** | Audit trail | Version history, git history, agent session logs | ✅ Yes |
| **E4** | Verifiable content checks | Phantom imports, unresolvable citations, leaked scaffolding | ✅ Free, high value |
| **E5** | Statistical & stylistic | Detectors, stylometry, punctuation, vocabulary | ⚠️ Unreliable alone |

**E4 is underrated.** Checking whether an imported package exists or a DOI resolves is free, deterministic, requires no vendor, and produces findings that survive challenge. Most people jump from E5 to accusation and skip it.

---

## 3. E1 — File provenance (C2PA)

### 3.1 What it is

A cryptographically signed manifest embedded in the file (JPEG APP11, PNG JUMBF boxes, video SEI). Records creating application, model, edit chain, signer. Any modification invalidates the signature, making it tamper-evident — which plain EXIF is not. **[P: C2PA spec]**

**Critical limit:** C2PA records what the creating tool *declares*. It does not analyse pixels. No manifest is not a negative result; it is no result.

### 3.2 `digitalSourceType` values to grep for

| URI | Meaning |
|---|---|
| `http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia` | Fully AI-generated media |
| `.../compositedWithTrainedAlgorithmicMedia` | AI-edited / inpainted |
| `.../algorithmicMedia` | Algorithmic, not model-derived |
| `.../compositeSynthetic` | Contains synthetic elements |
| `http://c2pa.org/digitalsourcetype/trainedAlgorithmicData` | AI-generated **data** (CSV, pickle) not media |

XMP properties: `DigitalSourceType`, `AISystemUsed`, `AISystemVersionUsed`, `AIPromptInformation`, `CreatorTool`.

### 3.3 Installation — none of these ship by default

```bash
# ExifTool
sudo apt install libimage-exiftool-perl        # Debian/Ubuntu
brew install exiftool                          # macOS

# c2patool — needs a Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install c2patool

# ripgrep
sudo apt install ripgrep   |   brew install ripgrep
```

### 3.4 Commands

```bash
c2patool image.png
for f in ./incoming/*.jpg; do echo "--- $f ---"; c2patool "$f" 2>/dev/null; done

exiftool -DigitalSourceType -FileName image.jpg
exiftool -Software -Description -UserComment image.png
exiftool -IPTC:all -XMP:all image.png
```

### 3.5 Public verifiers

| Tool | Covers | Cost |
|---|---|---|
| `openai.com/research/verify/` | OpenAI **images and audio** — C2PA + SynthID **[P]** | Free |
| OpenAI `content_provenance_checks` API | Programmatic; returns per-signal `outcome` and `validation_state` **[P]** | API pricing |
| `claude.com/check-content` | Claude-issued Content Credentials **[P]** | Free |
| `contentcredentials.org/verify` | General C2PA | Free |
| `c2patool` | CLI, full manifest dump | Free |
| `sightengine.com/c2pa-check` | Browser-side C2PA + EXIF/IPTC/XMP, edit-chain timeline | Freemium |

**Time cost:** seconds per file. Do this first, always.

### 3.6 What strips it

Screenshots. Format conversion. Re-saving. Social upload (Instagram, WhatsApp, most messengers strip EXIF and C2PA). Assume the signal is usually gone by the time content reaches you.

---

## 4. E2 — Provider watermarks

### 4.1 Status table

| Provider | Text | Images | Audio | Public detection |
|---|---|---|---|---|
| **Anthropic** | ✅ Fable 5.1, Mythos 5.1 only **[P]** | C2PA | — | ❌ Text: private preview. ✅ Files: free checker |
| **Google** | ✅ SynthID-Text since 2024 **[P]** | ✅ SynthID | ✅ SynthID | ⚠️ Restricted portal; **implementation open-sourced Apache 2.0, in HF Transformers** |
| **OpenAI** | ❌ None (built, shelved) | ✅ C2PA + SynthID (19 May 2026) **[P]** | ✅ SynthID (31 July 2026) **[P]** | ✅ **Free tool + API** |
| **xAI / Grok** | ❌ None; did not sign the Code | ❌ | ❌ | — |
| **Mistral, Cohere** | ⚠️ Signed; no documented mechanism **[U]** | — | — | — |
| **Meta / open-weight** | ❌ Structurally unenforceable | — | — | — |

Note the asymmetry: **OpenAI has no text watermark but the best public verification; Anthropic has a text watermark and no public verification.** Marking and letting people check are separable decisions, and vendors have made them differently.

### 4.2 Mechanism (SynthID-Text)

**Generate.** At position *t*: `r_t = Hash(key, x_{t-H}, …, x_{t-1})` (H small; H=3 and H=4 both appear in analyses; Anthropic's value is unpublished). The seed drives pseudorandom `g` functions scoring every candidate across *m* layers. Then **tournament sampling**: draw multiple candidates *from the model's real distribution*, run a knockout bracket where higher g-value advances, ties broken randomly. **[P: Nature]**

Secondary sources report ~30 layers in the published configuration **[S]**. Anthropic's configuration is unpublished.

**Detect.** Re-tokenize → recompute seeds → recompute g-values → average → hypothesis-test against baseline:

```
MeanScore = (1 / (m·T)) · Σ_t Σ_ℓ  g_ℓ(x_t, r_t)
```

Needs: the key, the **matching tokenizer**, the context window, the g-function spec. Does not need model weights or any model access.

**Honest caveats the marketing omits [P: Nature]:**
- Non-distortion does *not* mean a watermarked model gives the same response as an unwatermarked one.
- The paper reports **reduced inter-response diversity** in the non-distortionary configuration.
- DeepMind explicitly names tradeoffs among non-distortion, detectability, diversity, and compute.

### 4.3 Entropy is the binding constraint

| Strong signal | Weak or none |
|---|---|
| Creative writing, essays, narrative | Facts with one right answer |
| Translation (every word chosen) | Arithmetic, structured data, exact quotes |
| Code **comments** | **Code itself** |
| Long-form prose | Proofreading someone else's text |

Structural to all text watermarking, not a SynthID defect.

### 4.4 No published length threshold for Claude

**Anthropic has published no numeric threshold.** Only that detection "doesn't work well on small samples" and improves with length.

Figures circulating as "Claude requires 75–100 words" or "150–200 tokens" are **fabricated or misattributed**. The real numbers come from DeepMind's research on *Gemma*: roughly 80–90% TPR at 1% FPR around 400 tokens, degrading badly below ~50. Different model, different configuration, different key. **Do not cite these as Claude specifications.**

### 4.5 Attacks

**Watermark stealing** — Jovanović, Staab & Vechev, ETH Zurich SRI Lab, ICML 2024 **[P]**. API querying reverse-engineers the scheme enough to **scrub** and **spoof**. >80% average success for under $50, against green-list schemes; scrubbing rose from ~1% to >80% versus a prior baseline under 25%.

**Their separate SynthID-Text probing** — routinely conflated with the above. Against the deployed scheme: **spoofing success was limited and left detectable clues**; **paraphrase scrubbing exceeded 90%** at FPR 10⁻³; assisted scrubbing approaches ~100%. **[P: SRI blog]**

**Spoofing is the underrated half.** You can forge a mark onto human text. A *positive* detection is attackable, not just a negative one. Anyone acting on a detection needs to ask who benefits from planting it.

**Impossibility** — Zhang et al., ICML 2024: no watermark survives a bounded attacker willing to rewrite without visible quality loss. Demonstrated against KGW/EXP/Unigram and two vision schemes, **not SynthID-Text**. **[P]**

**Self-robustness failure** — arXiv 2603.03410 (March 2026, **preprint, not peer-reviewed [U]**): SynthID-Text under MeanScore shows *decreasing* separation as layers are added, and the authors argue this generalises to any mean-statistic detector.

**Images: UnMarker** — Kassis, University of Waterloo, IEEE S&P 2025. Universal attack removing **57%–100%** of detectable watermarks depending on scheme. **[S: IEEE Spectrum]**

**Human baseline for images:** a Microsoft study of 12,500 participants found people identify AI images at ~**62%** — barely above chance. **[S]** Eyeballing is not a method.

### 4.6 What a mark proves

- **Detected** → the model **may have processed** it. Cannot separate "wrote" from "heavily edited" from "translated."
- Says nothing about authorship or ownership.
- **Not detected** → nothing. Wrong version, wrong vendor, open weights, paraphrased, too short, stripped.

---

## 5. Base rates — the section v2 was missing entirely

This is the most important statistical content in the document, and it was absent.

Every false-positive discussion is meaningless without **prevalence**. What matters is not the false-positive rate but the **positive predictive value**: given a flag, what is the probability the person actually used AI?

With sensitivity ~95% and 10,000 items:

| True prevalence | FPR 1% | FPR 0.05% |
|---|---|---|
| **50%** | PPV ≈ 99% | PPV ≈ 99.9% |
| **10%** | PPV ≈ 91% | PPV ≈ 99.5% |
| **2%** | PPV ≈ 66% — **1 in 3 flagged people is innocent** | PPV ≈ 97% |
| **0.5%** | PPV ≈ 32% — **2 in 3 flagged people are innocent** | PPV ≈ 91% |

Read that carefully. **The same detector, unchanged, is trustworthy in one setting and actively harmful in another.** A tool with an excellent 1% FPR produces majority-innocent flags in a cohort where few people are cheating — which is exactly the cohort where you'd most want to trust it.

**Practical consequences:**

- Estimate your prevalence before deploying anything. If you can't, you cannot interpret your own results.
- Low-prevalence, high-stakes settings (professional misconduct, hiring, publication integrity) need FPRs an order of magnitude better than classroom settings, or a policy that never acts on the score alone.
- Prevalence is not stable. It rises term over term, which means your PPV silently improves while your absolute number of false accusations stays flat — and the affected individuals still exist.
- The absolute count matters more than the rate. 0.05% FPR across 100,000 submissions is 50 wrongly accused people.

---

## 6. Hybrid text — the modal real case

Most real documents are neither purely human nor purely AI. Human drafts, AI edits, human revises. Or AI drafts, human rewrites half. Nearly every framework — including v2's — is implicitly binary against a world that isn't.

**What the evidence says:** a 2026 peer-reviewed study (Hadra, Cambridge & Mesbah; 192 human, AI, and hybrid texts) reported Turnitin overall accuracy of **0.61**, and found **hybrid writing particularly difficult to classify**. **[S]** Another 2026 study (VUB) used a four-way ground truth — human, AI, hybrid, and "humanised" — precisely because the binary framing fails.

**How each evidence tier degrades on hybrid text:**

| Tier | Behaviour on hybrid |
|---|---|
| E1 C2PA | Binary and reliable, but only for files, and only tells you a tool touched it |
| E2 Watermark | **Degrades proportionally.** The mark lives only in model-chosen words. Light editing may leave it; heavy revision strips it. Anthropic: proofreading your own text may leave nothing detectable at all |
| E3 Audit trail | **Best tier for hybrid.** Version history shows the actual interleaving — where paste events sit among typed edits |
| E4 Content checks | Survives well. A phantom import is a phantom import regardless of who wrote the rest |
| E5 Detectors | **Worst.** Trained on binary labels, and degrade sharply |

**The framing problem.** "Was this AI-generated?" is usually the wrong question. Better: **"What was the human contribution, and does it meet the standard we set?"** That is answerable from E3 evidence, it maps onto actual policy, and — under **EU AI Act Article 50(4)** — AI text that has passed human editorial review with named editorial responsibility is *exempt* from the disclosure duty. The law already treats meaningful human involvement as the dividing line. Detection frameworks should too.

---

## 7. Code

Watermarking is structurally weak here (§4.3). **No reliable public AI-code detector exists.** Code forensics is provenance plus behavioural review.

### 7.1 Strongest signal: phantom dependencies

The model imports packages or calls endpoints that follow naming conventions perfectly and **do not exist**. Checkable, deterministic, near-impossible to produce accidentally. Also the basis of **slopsquatting** — registering hallucinated package names and waiting.

**Resolve every import and endpoint against the real registry.** This is E4 and it is the highest-value check in the document.

### 7.2 Provenance tooling

| Tool | Approach | Grade |
|---|---|---|
| **Cursor Blame** | Enterprise plan. Line-level: Tab vs Agent, which model, hover for conversation summaries. **Only sees Cursor sessions** | [P] |
| **agentdiff** | Git-native, **ed25519-signed**, cross-agent (Claude Code, Cursor, Copilot, Codex, Windsurf, OpenCode, Gemini). Agent, model, prompt excerpt, line ranges. Own git refs, no server. CI policy gates | [P] |
| **git-ai** | Git Notes at `refs/notes/ai`. Doesn't rewrite history. Multi-agent. On the Thoughtworks Technology Radar | [S] |
| **whogitit** | Similar, with prompt-content redaction | [S] |
| **Korext `ai-attestation`** | Open in-repo standard; claims 11+ tool detection | [S] |
| **Copilot code referencing** | Flags suggestions matching public code; logs repo, file, licence | [P] |
| **Copilot Metrics API** | Org-level suggestion/acceptance telemetry | [P] |

### 7.3 The trailer-forgery problem

**VS Code 1.118 made Copilot a Git co-author by default** for chat and agent commits, so `Co-authored-by: Copilot <copilot@github.com>` is now common. **[S]**

A plain-text git trailer is **metadata, not evidence**, and it fails in three directions:

- **Overcounts.** Default-on trailers mark commits where AI barely contributed, so any measurement of AI-assisted volume is inflated and legal or security review chases the wrong trail.
- **Undercounts.** One `git commit --amend` removes it.
- **Forgeable.** Anyone can insert it. If a dashboard treats the trailer as proof the code came from an approved tool, that is a supply-chain trust issue, not a bookkeeping one.

This is exactly why agentdiff signs attributions with ed25519 and writes to separate refs rather than into the commit message. Signed attestation in a namespace developers don't routinely touch is the difference between a record and a claim.

### 7.4 Repository forensics

```bash
git log --all --format='%h %ad %an <%ae> %s' --date=iso
git log --all --show-signature
git shortlog -sne
git log --all --grep='co-authored\|claude\|copilot\|cursor\|codex\|windsurf' -i
git log --all -S'Generated by' --source
git log --all --numstat            # find enormous single commits
git fetch origin '+refs/agentdiff/*:refs/agentdiff/*' || true   # if agentdiff in use
git notes --ref=ai list                                          # if git-ai in use
```

Look for: bot authors (`github-copilot[bot]`); one large single-commit implementation with no exploratory commits, no test iteration, no review-driven fixes; blocks arriving near-instantaneously per PR timestamps or CI logs.

None of that names a model. It establishes that code did not develop the way human code develops.

### 7.5 Security — usually the better argument

**Veracode 2026 GenAI Code Security Report (28 July 2026) [P]** — supersedes the 2025 edition:

- **~44% of AI code-generation tasks introduced a risky security vulnerability**; security pass rate **56%**, versus 55% in the first report. **Flat across four testing snapshots and 100+ models.**
- Meanwhile **syntax pass rates climbed from ~50% to >95%** since 2023. The gap between "code that works" and "code that works safely" is widening.
- **Cross-site scripting passed only ~15% of checks** (85% failure). **Log injection ~12%.** The Cloud Security Alliance independently measured XSS failure at 86% — close enough to treat as reproducible.
- Newer and larger models did **not** produce more secure code, suggesting a structural rather than temporary problem.
- In organisations that adopted AI coding tools, **AI now authors roughly half of committed code**.

For context on the reasoning: SQL injection and cryptography have decades of well-documented fix patterns in public code. Output encoding for XSS is framework- and context-dependent, which is harder to generalise.

**Use this.** "This has an unencoded user-facing output and no tests" is stronger, more actionable, and far less contestable than "Claude probably wrote this." It also doesn't require accusing anyone.

### 7.6 Behavioural indicators (weak, cluster them)

Over-commenting the obvious · uniform tutorial-voice comments · elaborate section banners in every small module · repeated generic `# TODO: Add error handling` · identical docstring templates regardless of complexity · comments referencing nonexistent variables · generic naming (`user_data`, `result`, `temp`) across unrelated modules · textbook architecture on a small task · unused imports · repeated generic try/catch with no domain recovery · happy-path-only tests · correct syntax with wrong business rules · style inconsistent with the rest of the repo.

**Explicitly NOT evidence:** `//`, `#`, `/* */`, `/** */`, `///` · JSDoc/JavaDoc/docstrings/OpenAPI · em dashes or `--` in comments · a README with a Quick Start · consistent formatting or linting. All produced by human conventions, IDE features, doc generators, and templates.

---

## 8. E5 — Detectors and stylometry

### 8.1 Accuracy landscape

- **Pangram** — claims 99.98% accuracy, ~1-in-10,000 FPR **[V]**. UChicago Booth and UMD researchers reported the lowest FPR of any tool tested **[S]**; tied first at 99.3% on COLING 2025 **[S]**. **Conflict note:** a substantial share of circulating Pangram evidence is Pangram summarising studies about Pangram. Weight accordingly.
- **VUB 2026 (peer-reviewed, 160 papers 4,000+ words)** — Turnitin, GPTZero and Copyleaks **completely failed** on fully AI-generated papers; Turnitin scored all 40 between 0–20% AI. Pangram: **65% strict, 97.5% inclusive**. *That 65% strict figure is not obviously "satisfactory" — v2 quoted both without reconciling them.* **[S]**
- **Hadra, Cambridge & Mesbah 2026** — Turnitin overall accuracy **0.61**; hybrid hardest. **[S]**
- **Originality.ai** — ~85% across 11 models on RAID; FPR reported 0.62%–9.24% depending on study. **[S]**
- OpenAI discontinued its own classifier in 2023 for inadequate accuracy.

### 8.2 Turnitin's 20% threshold **[P]**

Scores from **1% to 19% are suppressed**, shown as `*%` with no percentage and no highlights, because false positives are more likely in that range. In effect since July 2024.

- The "<1% false positive" claim covers **only documents above 20%**. It is not a general accuracy figure.
- Sentence-level FPR is substantially higher than document-level.
- **0% is not proof of human authorship.**
- Turnitin's own guidance: the report **should not be the sole basis for action**. Vanderbilt and others have disabled it entirely.

### 8.3 Systematic false positives

- **Non-native English speakers.** Stanford HAI (Liang et al.) found seven detectors misclassified **61.22% of TOEFL essays** by non-native writers as AI-generated. **[S] — important caveat v2 omitted: this is a 2023 study testing 2023-era detectors against GPT-3.5-era text.** The concern is almost certainly still live; that specific number is three model generations old. Cite it as evidence of a documented failure mode, not as a current measurement.
- Autistic writers; formally-trained technical, legal, scientific writers.
- Heavy Grammarly users.
- Formal academic tone and repeated domain terminology — both legitimately lower perplexity.
- Several popular detectors flag the **US Constitution** and the **Bible** as AI-generated.

Most detectors need ~80–150 words minimum, degrade badly on short text, and are weak outside English.

### 8.4 Multilingual — an under-covered gap

- **Detectors are trained predominantly on English.** Performance outside it is largely unmeasured, not merely lower.
- **Watermarks are language-agnostic in principle** — they operate on tokens, not semantics — but **tokenizer behaviour varies enormously by script.** Languages with poor tokenizer coverage produce more tokens per word, which changes the effective per-word signal density. Nobody has published per-language detection curves.
- **Code-switching and transliteration** (Hinglish, Thanglish, romanised Tamil/Hindi/Arabic) are the worst case for both. Low tokenizer efficiency, essentially no detector training data, and prose that already looks statistically unusual to an English-trained model.
- **Translation carries a full watermark** — every word is model-chosen. So a translated document is *more* detectable than an original, which is a strange incentive.
- If you deploy detection in a multilingual institution, the burden will not fall evenly. Assume it falls hardest on students and staff writing in their second or third language, and design the appeals process around that.

### 8.5 Invisible Unicode — artifacts, not watermarks

Copy-paste debris from chat-interface HTML rendering. Real watermarks add nothing; stripping these removes nothing forensic. Worth finding because they break CSV imports, code diffs, and regex.

| Codepoint | Name |
|---|---|
| `U+202F` | Narrow no-break space — strongest tell; ChatGPT emits it around em dashes and before units/`%` |
| `U+00A0` | Non-breaking space |
| `U+200B`–`U+200D` | Zero-width space / NJ / J |
| `U+2060` | Word joiner |
| `U+FEFF` | ZWNBSP / BOM |
| `U+00AD` | Soft hyphen |
| `U+200E`/`U+200F` | LTR / RTL marks |
| `U+2028` | Line separator |

```bash
LC_ALL=C.UTF-8 grep -P '[\x{00A0}\x{00AD}\x{200B}-\x{200F}\x{2028}\x{202F}\x{2060}\x{FEFF}]' file.txt
```

```python
import unicodedata
SUSPECT = {'\u00a0','\u00ad','\u200b','\u200c','\u200d','\u200e','\u200f',
           '\u2028','\u202f','\u2060','\ufeff'}
for i, ch in enumerate(text):
    if ch in SUSPECT:
        print(i, hex(ord(ch)), unicodedata.name(ch, '?'))
```

Both tested. The grep **requires** the locale prefix.

### 8.6 Stylometry

**`--` is a human tell** (ASCII typing, code, CLI flags). The **em dash `—`** is the AI-associated one. Also: en dash in numeric ranges, curly quotes in straight-quote contexts (mixed = paste splice), `…` over three periods, uniform spacing, zero typos.

**Build a comparative profile, never a keyword search:**

```
Punctuation:  hyphen/em-dash/en-dash/semicolon/colon/ellipsis freq · quote style
Sentence:     mean length · length VARIANCE · paragraph length · clause depth · passive %
Vocabulary:   type-token ratio · repeated words · rare words · adjective/adverb density
Structure:    heading/bullet/list patterns · conclusion patterns · templates
```

Compare against **the author's own baseline**, not an abstract AI profile. Deviation from a person's established writing means something. Matching a generic AI profile means almost nothing.

**Sentence-length variance is the highest-signal single feature.** Humans swing 4 to 40 words; models hover. That is what "burstiness" means operationally.

**Rhetorical patterns** — Anthropic named two itself: the **"this isn't [X], it's [Y]"** construction and overuse of **"quietly"**. Plus: colon-then-reveal · tricolon crescendo · "From X to Y" openers · participial tails · rhetorical question then immediate answer · both-sidesing resolving to "it depends" · hedge stacking.

**Structure:** heading-heavy output where none was needed · bold lead-in bullets repeated mechanically · rule of three everywhere · uniform 3–5 sentence paragraphs · emoji section markers · a "Conclusion" on something too short · **no orphan ideas** (everything resolves, nothing digresses — human writing leaks).

**Lexis:** delve, tapestry, testament, realm, landscape, journey, embark, navigate, foster, leverage, harness, unlock, elevate, underscore, showcase, streamline, bolster, resonate, quietly · intricate, nuanced, multifaceted, holistic, robust, seamless, pivotal, crucial, profound, meticulous, comprehensive, transformative, compelling, vibrant, nestled, myriad, plethora · cornerstone, beacon, catalyst, paradigm, ecosystem, tapestry, treasure trove, game-changer · "in today's fast-paced world" · "it's important to note" · "plays a crucial role in" · "a double-edged sword" · "ultimately, the choice depends on your specific needs."

**Register mismatch beats any single word.**

### 8.7 Leaked scaffolding (E4, not E5 — near-conclusive)

`:contentReference[oaicite:0]{index=0}` (ChatGPT citation object — essentially conclusive) · `【4:0†source】` · `<think>…</think>` (DeepSeek-R1, QwQ) · `<invoke>`, `<function_calls>` (Claude tooling) · dense `[1][2][3]` + Sources block (Perplexity) · "Sources and related content" (Gemini) · `\( \)` in non-math prose · `[Your Name]`, `[Insert Company]` · "As an AI language model" · "Certainly! Here's a…" · "Let me know if you'd like me to…" · `🤖 Generated with Claude` in commits.

---

## 9. Chain of custody

A report with no evidence handling does not survive challenge. v2 had none.

**Before analysis:**

```bash
sha256sum artifact.docx | tee artifact.sha256
date -u -Iseconds > acquisition-time.txt
cp artifact.docx artifact.docx.original   # never analyse the original
```

Record: how you obtained it, from whom, when (UTC), in what format, and whether it passed through any conversion.

**During:** work on the copy. Log every tool with its **version** (`exiftool -ver`, `c2patool --version`, detector model version and date). Detector models change; a score from March is not a score from September.

**After:** preserve raw tool output verbatim, not just your summary. Note what you did *not* check and why.

**Why it matters:** the person you flag may challenge the finding, and a detector score with no recorded tool version, no timestamp, and no preserved original is not defensible. Re-running a detector months later can produce a different number on identical text.

---

## 10. If you are the one accused

Absent from v1 and v2, and — given the base-rate arithmetic in §5 — at least as important as the detection side.

1. **Ask what the evidence actually is.** A percentage is not evidence. Which tier (§2)? A detector score, or a signed manifest? What tool, what version, what date?
2. **Cite the vendor's own limits.** Turnitin's documentation says the report should not be the sole basis for action, and suppresses its own scores below 20% because of false positives. **[P]** Anthropic's documentation says a detected mark shows processing, not authorship, and that absence of a mark proves nothing. **[P]** Vendors have already conceded the key points.
3. **Produce E3 evidence.** Version history is the strongest thing you have and it's usually already there. Google Docs and Word retain it automatically; Draftback and Revision History visualise it. Hundreds of incremental edits are very hard to fake and very easy to show.
4. **Preserve everything immediately.** Drafts, notes, browser history, search history, library records, earlier file versions. Do this before responding, because the record degrades.
5. **Offer to explain and modify it.** §11. If you wrote it, this is the strongest move available and it costs nothing.
6. **Name the base rate if relevant.** If you are in a low-prevalence, high-stakes setting, the PPV maths in §5 is a legitimate and quantitative argument, not a rhetorical dodge.
7. **If you are a non-native English writer, say so.** The Stanford HAI finding is a documented, citable failure mode, appropriately caveated as in §8.3.
8. **Do not degrade your writing to evade detectors.** It doesn't reliably work, it harms you, and detectors change faster than habits.

**Build the habit before you need it:** draft in a tool that keeps version history. It is the single cheapest insurance available, and it protects you whether or not you used AI.

---

## 11. Policy design

Arithmetic without process causes harm. If you are setting institutional policy:

**Define the standard, not the tool.** "AI-assisted work must be disclosed and the human contribution must be X" is enforceable and fair. "Do not use AI" is neither, and it collapses on hybrid text (§6).

**Set the threshold from base rates (§5), not the vendor's number.** Estimate prevalence. Compute expected false accusations in absolute counts. Decide whether that count is acceptable *before* deployment, and write it down.

**Never act on a score alone.** Make it a trigger for a conversation, never a finding. This is the vendors' own guidance.

**Require E1 or E3 corroboration** before any adverse action. A detector score plus version history showing a single paste event is a case. A detector score alone is not.

**Build the appeal first.** Who reviews it, on what evidence, with what burden of proof, and what happens to the record if the appeal succeeds.

**Publish your method.** Which tool, which version, which threshold, what corroboration is required. Undisclosed detection is not a fair process.

**Monitor disparate impact.** Track outcomes by first language and by disability status. Given §8.3 and §8.4, if you are not looking, you will not see it.

**Prefer artifact-quality arguments where they exist.** In engineering, §7.5 gives you a better and less adversarial route.

---

## 12. Worked example

*A 4,000-word report and its accompanying script, submitted for a role.*

| Step | Action | Result | Time |
|---|---|---|---|
| 1 | Hash, timestamp, copy | Custody established | 1 min |
| 2 | `c2patool` on all figures | 2 charts carry OpenAI C2PA, `trainedAlgorithmicMedia` | 2 min |
| 3 | `claude.com/check-content` on the PDF | No Claude credential | 1 min |
| 4 | Claude text watermark | **Not testable** — no public API, and if written on Opus 5, no mark exists to find | — |
| 5 | Scaffolding scan | One `:contentReference[oaicite:3]` in a footnote | 2 min |
| 6 | Resolve all 11 citations | 3 DOIs do not resolve; 1 quote misattributed | 25 min |
| 7 | Resolve all imports in the script | 1 of 9 does not exist on PyPI | 5 min |
| 8 | Version history | Not provided; requested | — |
| 9 | Detectors (2 tools) | 88% and 41% — disagree | 3 min |
| 10 | Stylometry vs. their published writing | Sentence-length variance markedly lower | 20 min |

**Findings.** E1 confirms two figures are OpenAI-generated. E4 is decisive on its own: a leaked ChatGPT citation object, three unresolvable DOIs, a misattributed quote, and a non-existent package. E5 disagrees with itself and adds nothing.

**Conclusion:** "Contains AI-generated figures (confirmed via C2PA) and shows unverified citations and a non-existent dependency." Not "88% AI." The E4 findings are the substance; they are checkable, they'd matter even if no AI were involved, and they don't require anyone to trust a detector.

**Total: ~1 hour.** The single most useful hour was step 6.

---

## 13. Report template

```
AI PROVENANCE ASSESSMENT

Artifact:     report.pdf  (sha256 3f2a…9c1)
Acquired:     2026-09-08T14:22:00Z, from <source>, as PDF
Analyst:      <name>
Tools:        exiftool 12.76 · c2patool 0.9.12 · <detector> model 2026-08-14

Assessment:   CONTAINS CONFIRMED AI-GENERATED ELEMENTS
              Text authorship: INDETERMINATE
Confidence:   HIGH (figures) · LOW (text)

E1  Cryptographic provenance
    C2PA on figures 2, 4        CONFIRMED   trainedAlgorithmicMedia, OpenAI
    C2PA on document            absent      (not a negative result)

E2  Provider watermark
    Claude text                 NOT TESTED  no public detector; source model
                                            may predate marking support
    OpenAI text                 N/A         no text watermark exists

E3  Audit trail
    Version history             REQUESTED, not provided
    Git history                 n/a

E4  Verifiable content checks
    Leaked scaffolding          1 instance  ChatGPT citation object, fn.14
    Citations                   3 of 11 DOIs unresolvable; 1 misattributed
    Dependencies                1 of 9 imports absent from PyPI

E5  Statistical
    Detector A / B              88% / 41%   detectors disagree
    Stylometric deviation       MODERATE    vs. author's published baseline

BASE RATE
    Estimated prevalence ~15%; detector FPR ~1%
    → PPV ≈ 94%. Not relied on; E4 findings are independent.

LIMITATIONS
  · No single signal establishes authorship.
  · Absence of a watermark is not evidence of human authorship.
  · Claude text watermarking covers only models launched on/after
    2026-08-02; the source model is unknown and may be exempt.
  · A positive watermark can be spoofed (Jovanović et al., ICML 2024).
  · Author has not yet been asked to explain or modify the work.

NOT CHECKED
  · Audio/video assets (none present)
  · Full stylometric corpus comparison (insufficient baseline)
```

---

## 14. The method that actually works

No foolproof detector exists. The most reliable verification is not technological.

**Ask the person to explain and modify it.**

1. Walk through it. What does this section do, and why is it here?
2. Modify it live. Change a function signature. Restructure paragraph three.
3. Justify decisions. Why this algorithm, this structure, this word?
4. What's missing? Which edge case did you decide not to handle, and why?
5. Show the process. Drafts, notes, test logs, version history.

If they cannot comfortably explain or adapt what they "wrote," that is stronger than any tool score and it survives appeal.

### 14.1 Triage worksheet — **uncalibrated, do not use for adjudication**

> **Warning.** These weights are invented. They are not validated against any dataset and have no calibrated relationship to actual probability. They order a review queue. Using this to reach a disciplinary finding would give arbitrary numbers the appearance of rigour — which is the same error as treating a detector percentage as a verdict.

| Weight | Signal |
|---|---|
| **+3** | Valid C2PA provenance on a supported asset |
| **+3** | Signed agent attestation or verified audit log |
| **+2** | Provider watermark verified by the provider's own detector |
| **+2** | Phantom import or unresolvable citation |
| **+1 ea.** | Leaked scaffolding · uniform redundant comments · generic TODOs · template docstrings · duplicated scaffolds · one-shot large commit |
| **−2** | Commit history shows iteration, issue-specific discussion, domain-aware fixes |
| **−2** | Author supplies drafts, test logs, and reasoning matching the artifact's evolution |

Say **"confirmed AI-processed"** only with provider-linked evidence. Otherwise: **"shows indicators consistent with AI-assisted work."**

---

## 15. Fifteen things to keep straight

1. **Watermark coverage is per-model-version, not per-vendor.** Fable 5.1 and Mythos 5.1 are marked. Opus 5 (24 July 2026), Sonnet 5, Haiku 4.5 are not, pending retrofit by 2 December 2026.
2. **This document is almost certainly unwatermarked**, on that basis.
3. **Real watermarks add nothing to the text.** Any "remover" that strips Unicode is removing artifacts, not watermarks.
4. **`--` is a human tell.** The em dash `—` is the AI one.
5. **OpenAI has no text watermark but the best public verifier** — images and audio, free, plus an API. Anthropic has the reverse.
6. **Two EU dates:** Article 50 applies from **2 Aug 2026**; pre-existing systems have until **2 Dec 2026** for Article 50(2) marking.
7. **Article 50(4) binds deployers**, with an exemption for AI text under human editorial review with named editorial responsibility. The law already treats meaningful human involvement as the line.
8. **A detected mark proves involvement, not authorship — and can be spoofed onto human text.**
9. **No mark proves nothing at all.**
10. **Watermarks are entropy-dependent.** Strong on creative prose and translation; weak to nil on facts, code, quotes, and proofreading.
11. **Paraphrasing defeats text watermarks** — >90% scrubbing against deployed SynthID-Text. Watermarking counters carelessness, not adversaries.
12. **Base rates decide everything.** The same detector is trustworthy at 50% prevalence and majority-wrong at 0.5%. Compute PPV before deploying.
13. **Hybrid text is the normal case** and it is where every method is weakest. "What was the human contribution?" beats "was this AI?"
14. **E4 checks are free, deterministic, and underused.** Resolve every import and every citation before touching a detector.
15. **Never accuse on style alone.** Every stylistic signal dies to one instruction or one paraphrase pass.

---

## Sources

**[P] Primary:**

- Anthropic — *How Claude's text watermark works* (14 Aug 2026, upd. 1 Sep 2026) — https://www.anthropic.com/news/claude-text-watermark
- Anthropic Help Center — *How Claude marks AI-generated content* — https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content
- Claude Content Checker — https://claude.com/check-content
- Anthropic detector access form — https://forms.gle/9tGA33hPJJwtHsMk9
- **OpenAI Verify (images + audio, free)** — https://openai.com/research/verify/
- OpenAI — *Advancing content provenance* (upd. 31 July 2026) — https://openai.com/index/advancing-content-provenance/
- OpenAI `content_provenance_checks` API — https://developers.openai.com/api/reference/resources/content_provenance_checks/methods/create
- Cursor Blame — https://cursor.com/docs/integrations/cursor-blame
- **agentdiff** — https://github.com/codeprakhar25/agentdiff
- Turnitin — AI writing detection model (20% threshold) — https://guides.turnitin.com/hc/en-us/articles/28294949544717-AI-writing-detection-model
- **Veracode 2026 GenAI Code Security Report** (28 July 2026) — https://www.veracode.com/blog/2026-genai-code-security-report-ai-risk/
- Veracode Spring 2026 update — https://www.veracode.com/blog/spring-2026-genai-code-security/

**Regulatory [P]:**

- Commission — Article 50 guidelines — https://digital-strategy.ec.europa.eu/en/policies/guidelines-ai-transparency-obligations
- Commission — Article 50 FAQ — https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act
- Commission — Quick Facts, Dec 2026 grace period — https://digital-strategy.ec.europa.eu/en/factpages/quick-facts-transparency-rules-ai-systems
- Commission — Code of Practice — https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content

**Research [P]:**

- Dathathri, See et al., *Scalable watermarking for identifying LLM outputs*, **Nature**, 23 Oct 2024 — https://www.nature.com/articles/s41586-024-08025-4
- Jovanović, Staab & Vechev, *Watermark Stealing in LLMs*, ICML 2024 — https://www.sri.inf.ethz.ch/publications/jovanovic2024watermarkstealing
- SRI Lab, *Probing DeepMind's SynthID-Text* — https://www.sri.inf.ethz.ch/blog/probingsynthid
- **Zhang, Edelman, Francati, Venturi, Ateniese & Barak**, *Watermarks in the Sand*, ICML 2024, PMLR 235:58851–58880 — https://proceedings.mlr.press/v235/zhang24o.html · code https://github.com/hlzhang109/impossibility-watermark
- Pangram technical report — https://arxiv.org/pdf/2402.14873
- *On SynthID-Text: Theoretical Analysis* — **preprint [U]** — https://arxiv.org/html/2603.03410v2

**Standards / trackers:**

- C2PA Implementation Guidance — https://spec.c2pa.org/specifications/specifications/2.4/guidance/Guidance.html
- **AI Watermarking Tracker** (CC BY 4.0 data) — https://aiwatermarking.org/data/

**Still unverified [U]** — Origin Lens · Erase Meta · AI Content Scanner · "$0.04 per pass" evasion figure · Copyleaks code-detection deprecation · Midjourney v8 / Sora 3 version specifics · Mistral and Cohere deployment status · any per-model token threshold attributed to Anthropic.

---

## 16. Disclosure

Written by Claude (Opus 5), which per §1 is not currently watermarked. Every primary source was fetched or searched during composition; grades in §0.4 mark what was verified directly versus taken from reporting. The two code snippets in §8.5 were executed and tested; the grep required correction. Three accusations of fabrication in v2 were checked and retracted in §0.1.

The document also trips most of its own §8.6 tells — heavy em dashes, bold lead-in bullets, rule-of-three, uniform paragraphs, no orphan ideas. That is not evidence of anything, which is the point the document keeps making.
