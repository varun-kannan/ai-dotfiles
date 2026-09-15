# AI Content Forensics — v4 Addendum
<!-- hygiene:ignore-file - quotes the patterns it documents -->

**Companion to v3. Sections 17–30. Verified 8 September 2026.**

v3 fixed the methodology (base rates, hybrid text, defence, chain of custody, policy) but silently regressed on breadth — video, audio, documents, generator metadata and model-specific habits were dropped in the rewrite, and several categories were never covered at all. This addendum closes those. v3's §0–§16 stand; nothing here supersedes them.

Source grades as in v3 §0.4: **[P]** primary · **[S]** secondary · **[V]** vendor · **[U]** unverified.

---

## 17. Documents — PDF, Office, slides, spreadsheets

Restored from v2 and expanded. This is E1/E3 evidence and it is routinely ignored in favour of much weaker E5 scores.

### 17.1 The strongest check available to any teacher or editor

**Version history.** AI text arrives as one large paste event; human writing accretes across hundreds of edits with pauses, deletions, and reordering.

- **Google Docs** — File → Version history. **Draftback** (Chrome extension) replays the entire document as a video. **Revision History** does similar.
- **Microsoft Word** — Version History via OneDrive/SharePoint; local files only if AutoRecover or tracked changes are on.
- **What you're looking for:** total edit sessions, the largest single insertion, ratio of typed characters to pasted characters, and whether the document grew linearly or appeared in blocks.

No detector, no vendor, no cost, and it survives appeal in a way a percentage never will. It is also the single best thing to preserve if you are the one accused (v3 §10).

### 17.2 PDF metadata

```bash
exiftool -Producer -Creator -CreateDate -ModifyDate -Author doc.pdf
pdfinfo doc.pdf
strings doc.pdf | grep -a -i -E 'producer|creator|xmp' | head -40
```

| `Producer` / `Creator` value | Implies |
|---|---|
| `Skia/PDF` | Chrome print-to-PDF or Google Docs export |
| `Microsoft: Print To PDF` | Windows print pipeline |
| `LaTeX with hyperref` / `pdfTeX` | LaTeX authoring — strong human-workflow signal |
| `Microsoft® Word for Microsoft 365` | Native Word export |
| Canvas/headless-browser exporters | Programmatic generation |
| Empty or absent | Stripped, converted, or scrubbed |

**Interpretation:** an essay whose `Producer` is `Skia/PDF` was printed from a browser. That's consistent with pasting text into Google Docs, and equally consistent with a student who simply uses Google Docs. It's a lead, not a finding.

### 17.3 DOCX internals

A `.docx` is a ZIP. Open it.

```bash
mkdir -p /tmp/docx && cd /tmp/docx && unzip -o ../file.docx > /dev/null
cat docProps/core.xml    # creator, lastModifiedBy, revision, created, modified
cat docProps/app.xml     # TotalTime, Words, Pages, Application, Company
```

| Field | Signal |
|---|---|
| `<cp:revision>1</cp:revision>` | Document saved once. Consistent with paste-and-submit |
| `<TotalTime>0</TotalTime>` | Zero minutes of recorded editing |
| `dcterms:created` == `dcterms:modified` | Created and finished in the same instant |
| `<dc:creator>` vs `<cp:lastModifiedBy>` | Different names = the file passed through someone else |
| `<Application>` | Which suite wrote it |

Same for `.pptx` and `.xlsx` — identical ZIP structure, same `docProps/`.

**Caveat:** `TotalTime` is unreliable across converters, Google Docs round-trips, and LibreOffice. Absence of editing time is weak; presence of substantial editing time is meaningfully exculpatory.

### 17.4 Slides and spreadsheets

- **PPTX** — uniform slide structure, every slide using the same layout, speaker notes in identical tutorial voice, no orphan/abandoned slides. Check `docProps/app.xml` `TotalTime`.
- **XLSX** — formulas that are structurally identical across unrelated columns; no manual overrides anywhere; no stray formatting; no leftover scratch cells. Real spreadsheets are messy. Check for `_xlfn.` prefixes indicating formulas written for a different Excel version than the one that saved the file.

### 17.5 CMS and email paste artifacts

HTML pasted from a chat UI carries the source stylesheet: `<span style="white-space: pre-wrap">`, `data-*` attributes, or class names matching a known interface. View source before publishing, and grep for `U+202F` (v3 §8.5).

---

## 18. Images — generator-specific metadata

v3 §3 covers C2PA and IPTC. This is the per-generator layer that got dropped, and it is often more informative than C2PA because **unsigned metadata is verbose**.

| Generator | C2PA | What it writes |
|---|---|---|
| **DALL·E 3 / ChatGPT** | ✅ Signed by OpenAI **[P]** | EXIF `Software` ≈ "DALL-E 3 via ChatGPT"; IPTC `DigitalSourceType` = `trainedAlgorithmicMedia`; SynthID since 19 May 2026 |
| **Midjourney** | ❌ None as of early 2026 **[S]** | Very rich unsigned metadata: `Description` holds the **full prompt with parameters** (`--ar`, `--stylize`, `--chaos`), `Author` holds the username, `Digital Image GUID` holds the Job ID as a UUID, and it does set `DigitalSourceType` |
| **Stable Diffusion (A1111, ComfyUI)** | ❌ | `parameters` / `UserComment` PNG text chunk with prompt, negative prompt, sampler, steps, CFG scale, seed, **model checkpoint hash** |
| **Adobe Firefly** | ✅ | Content Credentials; optional visible mark |
| **Google Imagen / Gemini** | ✅ | SynthID (pixel) + C2PA |
| **Leonardo, Meta AI** | ⚠️ Partial **[U]** | Varies by export path |

**The asymmetry worth exploiting:** Midjourney has no cryptographic provenance but leaks the entire prompt and the user's handle in plaintext. Stable Diffusion leaks the checkpoint hash, which can identify the exact model. Neither is signed — so neither is *proof* — but both are far more informative than a C2PA manifest that only says "AI-generated."

```bash
exiftool -Description -Author -Parameters -UserComment -DigitalImageGUID img.png
exiftool -a -G1 -s img.png | grep -i -E 'prompt|seed|sampler|model|job'
```

### 18.1 Pixel-level analysis is now the weakest layer

A Microsoft study of 12,500 participants found people identify AI images at ~**62%** — barely above chance. **[S]** And **UnMarker** (Kassis, Waterloo, IEEE S&P 2025) removes **57%–100%** of detectable image watermarks depending on scheme. **[S]**

Eyeballing was never a method. Now the watermarks it was supposed to replace are also attackable. Provenance metadata and source context are what remain.

---

## 19. Video

The thinnest evidence layer, and the most consequential. Restored and expanded.

### 19.1 Provenance

- **C2PA supports video** via SEI markers in the bitstream and container-level manifests, but deployment is uneven. Runway and Pika attach Content Credentials to output by default; Sora attaches C2PA. **[S]**
- **`c2patool` video support is limited.** Expect partial manifest extraction and verify manually.
- **Re-encoding destroys it.** Every platform re-encodes on upload. Assume C2PA is gone on anything from social media.

```bash
c2patool video.mp4
ffprobe -v quiet -print_format json -show_format -show_streams video.mp4
exiftool -Encoder -HandlerDescription -CreateDate -Software video.mp4
mediainfo --Output=JSON video.mp4
```

Container metadata sometimes names the tool: `Encoder`, `WritingLibrary`, `HandlerDescription`. Frame-rate and resolution combinations that match no camera (e.g. exactly 1024×576, 24fps, 4.0s duration) are a generation signature in themselves — AI video tools produce characteristic dimensions and lengths.

### 19.2 Artifact analysis

Ordered by durability as models improve:

| Signal | Notes |
|---|---|
| **Temporal inconsistency** | Objects changing shape, count, or texture across frames; background elements that drift |
| **A/V desync** | Lip movement not matching phonemes, especially on plosives and sibilants |
| **Face-swap boundaries** | Blending seams at the jawline and hairline, visible under sharpening |
| **Physics violations** | Cloth, hair, water, and reflections that don't conserve; shadows inconsistent with light sources |
| **Frame-rate artifacts** | Interpolation ghosting where a model upsampled |
| **Hands, text, and crowds** | Still the hardest for generators — but improving fastest, so weakest long-term |

Extract and inspect frames rather than watching:

```bash
ffmpeg -i video.mp4 -vf fps=2 frames/%04d.png
ffmpeg -i video.mp4 -vf "select='gt(scene,0.3)',showinfo" -vsync vfr scenes/%03d.png
```

### 19.3 Honest position

For video, **provenance and source context beat detection**. Where did this file come from, who published it first, does it appear anywhere before the claimed date, does an original higher-resolution version exist? Reverse image search on extracted keyframes often resolves it faster than any artifact analysis. Detection-by-artifact is a losing rearguard action and should be your last resort, not your first.

---

## 20. Audio, voice, and music

Never adequately covered in any version. This is where the immediate real-world harm sits — vishing, fraud, and identity attacks.

### 20.1 Provenance first

- **OpenAI Verify** (`openai.com/research/verify/`) checks **audio** for C2PA and SynthID, free, with an API. Covers ChatGPT and API audio since 31 July 2026. **[P]** This is the strongest publicly available audio check that exists.
- **Google SynthID Audio** — deployed, detector restricted. **[P]**
- **Suno** embeds C2PA Content Credentials at generation time. A valid Suno manifest is definitive regardless of how human the vocal sounds. **[S]**
- **Resemble Watermarker** — commercial watermarking at generation. **[V]**

### 20.2 Detection tools

| Tool | Domain | Grade |
|---|---|---|
| **Pindrop** | Call-centre voice authentication and deepfake detection | [S] |
| **Resemble Detect** | Audio deepfake detection (from a voice-cloning company — note the incentive) | [V] |
| **Hiya** | Call screening with deepfake detection | [S] |
| **AASIST**, **wav2vec2-based spoofing models** | Open research models; **ASVspoof 2019** is the standard benchmark database | [P] |

### 20.3 What the research actually says about difficulty

The **RADAR Challenge 2026** (Robust Audio Deepfake Recognition under Media Transformations) evaluated systems on **100,000+ utterances across English, Singapore English, Mandarin, Taiwanese Mandarin, Japanese, and Vietnamese**, scored by equal error rate. 33 teams entered the development phase, 22 the final. The published conclusion is that robust detection **under multilingual and media-transformed conditions remains unsolved**. **[P]**

Read that as: telephony compression, re-encoding, and non-English speech each degrade audio deepfake detection substantially. If your use case involves a phone call in a language other than English, current detection is weak.

### 20.4 A finding that complicates the whole approach

A 2026 paper, *The Watermark Shortcut: How Provenance Marking Sabotages Audio Deepfake Detection* (arXiv 2606.23335), argues that training detectors on watermarked synthetic audio teaches them to detect **the watermark** rather than **the synthesis**. **[U — preprint]**

If that holds, detectors trained on marked data will fail precisely on unmarked audio from adversaries who disabled watermarking — the exact case that matters. It is a specific instance of a general risk: **watermarks and detectors are not additive, and one can quietly undermine the other.**

### 20.5 Music

- Suno and Udio attach C2PA. Check it first — it settles the question when present.
- **Suno v5.5 "Voices"** (26 March 2026) clones real vocals into generated tracks, which pushes vocal-based detection toward inconclusive verdicts. **[S]** Detectors compensate by analysing the whole generation architecture — spectral characteristics in the 2–8 kHz band, instrumental synthesis patterns — rather than the voice alone.
- Practical consequence: **a human-sounding vocal no longer means a human track.** Check provenance and distributor metadata, not your ears.

### 20.6 Voice fraud — the operational advice

Detection is too slow and too unreliable for a live call. The controls that work are procedural:

- **Verify through a separate channel.** Hang up, call back on a known number.
- **Use a pre-agreed family or team code word** for urgent money and identity requests.
- **Treat urgency as the signal.** Manufactured time pressure is the constant across voice-fraud cases, regardless of how good the clone is.

Note that a browser-side voice detector cannot decode SynthID or verify C2PA cryptographically — it does waveform triage only. Useful as a first pass, not as evidence.

---

## 21. AI-generated data

v3 cited the `trainedAlgorithmicData` C2PA URI and never developed it. Fabricated datasets, synthetic survey responses, and invented results are a distinct category with their own mature methods — most of which predate LLMs and are unaffected by them.

### 21.1 The scale of the survey problem

Research on online survey integrity reports usable-response rates falling from roughly **75% to 10%** as AI-powered bots and sophisticated fraud entered the pipeline. **[S]** For anyone running online surveys, this is now the dominant data-quality problem.

### 21.2 Benford's Law

The leading significant digit of many natural datasets follows a logarithmic distribution — more 1s than 2s, more 2s than 3s. Humans fabricating numbers do not reproduce this. **[P]**

**Applied successfully to:** retracted publications by Hunton, Stapel, Walumbwa, Lichtenthaler and Sato, which deviated significantly from the Benford distribution relative to controls, after adjusting for article characteristics. **[P]** Also used against survey interviewer fraud, where inexperienced interviewers showed higher falsification rates concentrated in early assignments.

**Preconditions — this is where people misuse it:**
- Data must span several orders of magnitude
- Must be positively skewed
- **Must have no built-in maximum or minimum**
- Sufficient continuous values

**It does not work on** Likert scales, percentages, ages, bounded measurements, assigned identifiers, or anything with a natural cap. Applying it there produces confident nonsense. Use **Sison & Glaz confidence intervals** for the multinomial test, and a **modified/generalized Benford** analysis with a cutoff log-normal where accounting limits exist — this materially reduces false positives.

```python
import numpy as np
from collections import Counter

def benford(values):
    lead = [int(str(abs(v)).lstrip('0.').replace('.','')[0])
            for v in values if v and str(abs(v)).lstrip('0.')]
    obs = Counter(lead); n = len(lead)
    exp = {d: np.log10(1 + 1/d) for d in range(1, 10)}
    chi2 = sum((obs.get(d,0) - exp[d]*n)**2 / (exp[d]*n) for d in range(1,10))
    return {d: (obs.get(d,0)/n, exp[d]) for d in range(1,10)}, chi2, n
# chi2 > 20.09 at df=8 → p < 0.01. n < 100 → do not interpret.
```

### 21.3 Other statistical forensics

| Method | Detects |
|---|---|
| **GRIM test** | Reported means that are arithmetically impossible for the stated sample size with integer data |
| **GRIMMER** | Same logic extended to standard deviations and variances |
| **Terminal digit analysis** | Uniform expected in the last digit; human fabrication clusters on 0 and 5 |
| **Variance analysis** | Fabricated data is characteristically *under*-dispersed — humans avoid producing outliers |
| **Duplicate detection** | Exact or near-exact repeated rows; identical response vectors across "different" respondents |
| **Response-time distributions** | Impossibly fast completions; suspiciously uniform per-question timing |
| **Straight-lining / patterned responding** | Same option throughout, or a repeating pattern |
| **Attention-check failure clustering** | Correlated failures across supposedly independent respondents |
| **Open-text analysis** | Apply v3 §8 to free-text fields — LLM-generated survey answers carry the same lexical and structural tells |

### 21.4 Interpretation

These are E4-class checks — deterministic, checkable, and independent of any vendor. Like phantom imports, they identify a problem that matters **whether or not AI was involved**. Fabricated data is a finding on its own terms, which makes it both stronger and less adversarial than an authorship accusation.

---

## 22. Academic and publishing forensics

Never covered. It is the most mature applied AI-detection ecosystem in existence, with real retraction outcomes behind it.

### 22.1 The Problematic Paper Screener

Built by **Guillaume Cabanac** (Université de Toulouse) with **Cyril Labbé** (Université Grenoble Alpes), starting around 2020–21 after ~40 obviously machine-generated papers were found to have cleared peer review. **[P]**

- Trawls **130–160 million papers** indexed in Dimensions, **weekly**
- Runs **nine detectors**, not one
- Over **7,500 tortured phrases** in the fingerprint list as of September 2025
- Flags papers with **five or more** tortured phrases, deliberately, to suppress false positives
- Results posted publicly and reviewed by a crowdsourced network of sleuths, with findings taken to **PubPeer**
- **More than 3,000 retractions** attributed to this work **[S]**
- Several major publishers now screen at submission rather than post-publication

### 22.2 Tortured phrases

Machine-paraphrased scientific terms — grammatically fine, scientifically meaningless. Real documented examples:

| Tortured | Actual term |
|---|---|
| bosom peril | breast cancer |
| kidney disappointment | kidney failure |
| fake neural organization | artificial neural network |
| lactose bigotry | lactose intolerance |
| Joined Together States | United States |
| formic corrosive | formic acid |
| weighty metals | heavy metals |
| man-made consciousness | artificial intelligence |
| enormous information | big data |
| randomized controlled preliminary | randomised controlled trial |
| **surface region** | surface area — the most common, found in ~42,500 papers |

**Critical caveat, stated by the tool's own community:** a tortured phrase is evidence of **paraphrasing-tool use**, not proof of fabricated results. Genuine research can be reported in tortured phrasing if an author or an editing vendor ran the text through a spinner. It is a screening trigger, not a verdict.

### 22.3 The other detectors

- **ChatGPT fingerprints** — the leaked-scaffolding class from v3 §8.7, found in published literature. Authors pasting output without reading it.
- **SCIgen / Mathgen gibberish** — grammar-generated nonsense papers, identified by fingerprint word sequences characteristic of the generator's context-free grammar.
- **"Clay feet"** — papers whose citations point at already-flagged problematic papers. Paper-mill output tends to cite other paper-mill output, which makes citation graphs a detection surface in their own right.

### 22.4 Ecosystem

**STM Integrity Hub** · **Clear Skies Papermill Alarm** · **COPE** (flowcharts and paper-mill guidance) · **United2Act** · **PubPeer** (post-publication review) · **Retraction Watch**.

### 22.5 The honest assessment from inside the field

Cabanac himself characterises detection as an arms race that is probably ultimately unwinnable, and acknowledges the tools only catch **crude** fraud. **[S]**

And a point every institution should absorb, from a publishing-integrity practitioner: **adding a few typos is often enough to defeat AI text detection, because models don't make typos.** **[S]** A detector that a deliberate misspelling defeats is not a security control. It is a filter for carelessness — which is genuinely useful, and is all it is.

---

## 23. Full detector roster with measured false-positive rates

v3 covered five commercial tools. Here is the real landscape, including the academic methods, and — more importantly — **independently measured FPRs**.

### 23.1 The RAID benchmark FPR table

From RAID (arXiv 2405.07940), measured false-positive rates at four threshold choices. **This table is the most useful thing in this addendum.** **[P]**

| Detector | t=0.25 | t=0.5 | t=0.75 | t=0.95 |
|---|---|---|---|---|
| **GPTZero** | 0.03% | 0.00% | 0.00% | 0.00% |
| **Binoculars** | 0.07% | 0.00% | 0.00% | 0.00% |
| **Originality** | 0.47% | 0.25% | 0.17% | 0.07% |
| **Winston** | 0.75% | 0.55% | 0.38% | 0.21% |
| **ZeroGPT** | 1.71% | 1.42% | 1.21% | 0.90% |
| **RADAR** | 7.48% | 3.48% | 2.17% | 1.23% |
| **Fast-DetectGPT** | 47.3% | 23.2% | 13.1% | 1.70% |
| **LLMDet** | 97.9% | 96.0% | 92.0% | 75.3% |
| **GLTR** | 100% | 99.3% | 21.0% | 0.05% |

The paper's own conclusion: for some detectors, **naive thresholding produces unacceptable false-positive rates**.

Three things to take from this:

1. **The threshold matters as much as the tool.** GLTR ranges from 100% FPR to 0.05% across four threshold choices of the same detector on the same data.
2. **Some widely-cited academic methods are unusable at default settings.** LLMDet at 97.9% FPR is flagging essentially everything.
3. **Metric-based methods (Binoculars, Fast-DetectGPT) generalise across domains surprisingly well** — which is not what most people assume about zero-shot approaches.

Feed these numbers into v3 §5's base-rate arithmetic before choosing anything.

### 23.2 Binoculars — the method worth knowing

**[P: arXiv 2401.12070, Hans et al.]** Scores text by contrasting **two closely related language models** — a cross-perplexity metric that corrects for the fact that perplexity alone conflates "predictable text" with "machine text."

- **>90% TPR at 0.01% FPR** on ChatGPT output, **zero-shot**, no training on ChatGPT data
- Outperformed Ghostbuster, GPTZero, DetectGPT, Fast-DetectGPT and DNA-GPT in the original evaluation
- Works on **black-box** models without needing next-token probabilities — unlike DetectGPT, Fast-DetectGPT and GLTR, which require white-box access
- Reported as resistant to prompt-based evasion strategies
- Open source: `github.com/ahans30/Binoculars`

**Caveat:** the headline figures are from the authors' own evaluation. RAID's independent measurement (§23.1) is consistent, which is reassuring, but treat the original numbers as best-case.

### 23.3 The academic family

| Method | Approach | Access needed |
|---|---|---|
| **GLTR** | Token-rank visualisation; the original 2019 approach | White-box |
| **DetectGPT** | Probability-curvature under perturbation | White-box |
| **Fast-DetectGPT** | Conditional probability curvature; much faster | White-box |
| **DNA-GPT** | Divergent n-gram analysis via suffix prediction | API |
| **Ghostbuster** | Structured search over model features | Black-box |
| **RADAR** | Adversarially trained detector | Black-box |
| **Binoculars** | Cross-perplexity between paired models | Black-box |

### 23.4 Commercial roster

Beyond v3's five: **Winston AI**, **Sapling**, **ZeroGPT**, **Scribbr**, **Smodin**, **Copyleaks**, **Crossplag**. Treat all vendor-published accuracy figures as **[V]** until independently replicated — including Pangram's, as flagged in v3 §8.1.

### 23.5 The methodology that actually reduces false positives

From a 2026 news-domain study **[P: arXiv 2508.06445]** worth copying wholesale:

1. **Establish a pre-GPT baseline.** They ran detectors against ~17,000 Washington Post articles published 2012–2017 — text that is definitionally human. Measured accuracies: **Binoculars 99.96%, GPTZero 99.88%, Fast-DetectGPT 97.03%**.
2. **Select only detectors that pass your own baseline**, in your own domain.
3. **Require majority voting.** They labelled an article AI-generated only when **at least 2 of 3** detectors agreed.

This is the correct pattern for anyone deploying detection at scale, and it costs nothing but effort. A single detector score is not a method; a validated ensemble with a domain-specific baseline is.

---

## 24. Humanisers and paraphrasers — the inverse tells

Dropped after v1. This matters because paraphrasing is **the** effective attack: >90% watermark scrubbing (v3 §4.5), and it collapses detector performance generally.

**The ecosystem:** QuillBot, Undetectable.ai, StealthGPT, HIX Bypass, WriteHuman, Humanize AI, plus older spinners (SpinBot) that produced the tortured phrases in §22.

**The inverse tells — evidence of *evasion*, which is arguably worse than evidence of use:**

- **Thesaurus damage.** Synonym substitutions that miss register or collocation: "use" → "capitalise on", "big" → "considerable", "show" → "evince". This is exactly the mechanism that generates tortured phrases.
- **Broken idioms and fixed expressions.** Idioms only work verbatim; a spinner breaks them. "The proof is in the pudding" → "the evidence resides within the dessert."
- **Contorted syntax.** Sentences restructured for no communicative reason — clauses inverted, passives introduced, subordination added where the meaning didn't require it.
- **Terminology drift.** A technical term rendered three different ways in one document, because the tool synonymised inconsistently.
- **Deliberately injected typos.** The known bypass. **Look for typos that are inconsistent with the author's other errors** — a document with perfect grammar, sophisticated vocabulary, and three random character transpositions is a strange artifact.
- **Unnatural sentence-length variance.** Some tools now inject variance specifically to defeat burstiness metrics, producing distributions that are *too* varied — bimodal rather than natural.
- **Semantic drift.** Content that has been paraphrased until claims subtly no longer match their citations.

**Detection status:** Turnitin added bypasser detection in Aug 2025 **[S]**; the VUB 2026 study used a four-way ground truth including a "humanised" class precisely because it's a distinct category. **[S]**

**The strategic point:** evasion evidence is often more actionable than use evidence. Using AI may be permitted. Deliberately defeating a disclosed detection process rarely is, and it demonstrates intent in a way that a detector percentage never can.

---

## 25. Model-specific style habits

Restored from v2. Weak individually **[E5]**; people triangulate with them.

| Model | Habits |
|---|---|
| **ChatGPT (GPT-4o/5)** | Em dash volume, `U+202F`, "Certainly!", bold lead-in bullets, emoji headers, "Here's the thing:", closing "Want me to…?", LaTeX delimiters, `contentReference` leakage, listicle bias |
| **Claude** | Longer flowing paragraphs, fewer bullets, "I should note", "That said", reasoning-out-loud, explicit tradeoffs, XML-ish tags if tooling leaks. **Watermarked only on Fable 5.1 / Mythos 5.1** (v3 §1) |
| **Gemini** | Heavy `**bold**` mid-sentence, "Sources and related content", tabular comparisons, SynthID-Text |
| **Copilot** | Superscript citations, hedged corporate register, "I'd be happy to help with that" |
| **Perplexity** | Dense `[1][2][3]`, short paragraphs, source list at end |
| **Grok** | More colloquial, willing to be blunt, X post citations, **no watermark** |
| **DeepSeek / QwQ / R1** | `<think>` leakage, long visible reasoning chains, occasional Chinese tokens |
| **Llama / Mistral fine-tunes** | "As a helpful assistant", repetitive sentence openers, weak transitions |
| **Jasper / Copy.ai / Writesonic** | Marketing cadence, "Imagine a world where…", CTA at the end |
| **Grammarly-heavy human text** | Reads AI-ish. A very common false positive |

**Health warning:** these are the weakest signals in the entire document and they decay with every model release. Vendors actively tune away from known tells. Never use this table for anything but generating a hypothesis to test with E1–E4 evidence.

---

## 26. The legal and privacy exposure of running detection

Absent from every version, and the section most likely to matter to an organisation.

### 26.1 You are processing personal data

Under **GDPR** and India's **DPDP Act 2023**, analysing someone's writing to infer authorship is processing of personal data, and generates new personal data (the score). That triggers:

- **Lawful basis.** Legitimate interest is arguable but requires a documented balancing test. Consent is unreliable where there is a power imbalance — students and employees cannot freely refuse.
- **Transparency.** Data subjects must be told detection is in use, on what basis, and what happens to results. **Undisclosed detection is difficult to defend under any framework.**
- **Purpose limitation.** A detector run for academic integrity cannot be repurposed for performance management.
- **Retention.** Decide how long scores and flagged documents persist. Indefinite retention of "suspected of cheating" records is a real liability.
- **Access and rectification.** The subject can request the score and challenge it. Your chain-of-custody record (v3 §9) is what makes that answerable.

### 26.2 Third-party detectors are data transfers

Uploading student essays, employee writing, or client material to a commercial detector transfers it to a processor, often across borders. That needs a **DPA**, a transfer mechanism, and confirmation of the vendor's retention and training practices. **Check whether the vendor trains on submitted content** — several have.

Confidential material (unpublished manuscripts, legal drafts, client work, source code) should not go into a third-party detector at all. Prefer **locally-run** methods — Binoculars, Fast-DetectGPT, ExifTool, `c2patool` — where confidentiality matters.

### 26.3 Automated decision-making

GDPR Article 22 restricts decisions based solely on automated processing with legal or similarly significant effects. An automated academic-integrity or hiring decision driven by a detector score sits close to that line. **Meaningful human review is not just good practice here; it is likely a legal requirement.**

### 26.4 Discrimination exposure

Given the documented failure modes (v3 §8.3, §8.4), a detection regime that disproportionately flags non-native speakers or disabled writers is a discrimination risk under equality legislation in most jurisdictions, independent of intent. **Monitor outcomes by group. If you are not measuring it, you cannot defend it.**

### 26.5 Defamation and employment

Stating that someone used AI, when your evidence is a probabilistic score, carries defamation risk if communicated beyond those with a need to know, and unfair-dismissal risk if it grounds termination. Use "shows indicators consistent with" language (v3 §14.1), restrict circulation, and document the corroborating evidence.

---

## 27. Decision flow

```
                    ┌─────────────────────┐
                    │  Hash · timestamp   │
                    │  Work on a COPY     │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │ Is it a FILE with   │
                    │ a media container?  │
                    └─────┬─────────┬─────┘
                       yes│         │no
                          ▼         │
              ┌────────────────────┐│
              │ E1: C2PA + EXIF    ││
              │ c2patool, exiftool ││
              │ OpenAI Verify      ││
              └─────────┬──────────┘│
                        │           │
              manifest? │           │
             ┌──────────┴───────┐   │
          yes│                  │no │
             ▼                  ▼   ▼
      ╔═════════════╗   ┌──────────────────────┐
      ║ CONCLUSIVE  ║   │ E3: audit trail      │
      ║ Report & stop║   │ version history      │
      ╚═════════════╝   │ git log · agent logs │
                        └──────────┬───────────┘
                                   │
                        strong?    │
                     ┌─────────────┴────────┐
                  yes│                      │no
                     ▼                      ▼
              ╔═════════════╗   ┌────────────────────────┐
              ║   STRONG    ║   │ E4: verifiable checks  │
              ║ Corroborate ║   │ · resolve every import │
              ╚═════════════╝   │ · resolve every DOI    │
                                │ · scaffolding scan     │
                                │ · Benford / GRIM       │
                                │ · tortured phrases     │
                                └──────────┬─────────────┘
                                           │
                               any failure?│
                            ┌──────────────┴──────┐
                         yes│                     │no
                            ▼                     ▼
                     ╔═════════════╗   ┌────────────────────┐
                     ║  ACTIONABLE ║   │ E5: detectors      │
                     ║  regardless ║   │ ONLY IF:           │
                     ║  of AI      ║   │ · baseline done    │
                     ╚═════════════╝   │ · ≥2 of 3 agree    │
                                       │ · PPV computed     │
                                       └─────────┬──────────┘
                                                 ▼
                                       ┌────────────────────┐
                                       │ ASK THEM TO        │
                                       │ EXPLAIN & MODIFY   │
                                       │ (always, any path) │
                                       └────────────────────┘
```

**The shortcut most people miss:** if E4 turns up a non-existent package or an unresolvable DOI, you have an actionable finding that does not require proving AI authorship at all. Stop there. It's cleaner, it's checkable, and it doesn't require accusing anyone of anything.

---

## 28. Costs, rate limits, and time

Never covered. Budget before designing a pipeline.

| Check | Tooling cost | Time per item | Notes |
|---|---|---|---|
| Hash + custody | Free | <1 min | Non-negotiable |
| `c2patool` | Free (Rust build) | seconds | Batchable |
| ExifTool | Free | seconds | Batchable; the workhorse |
| `claude.com/check-content` | Free | seconds | Manual upload; no public API |
| **OpenAI Verify** | Free (web) | seconds | API billed; **the best free verifier** |
| OpenAI provenance API | API pricing | seconds | Structured `outcome` + `validation_state` |
| Anthropic text detection | N/A | — | **Private preview; no public access** |
| Version history review | Free | 5–15 min | Highest value per minute spent |
| Git forensics | Free | 5–20 min | Scriptable |
| **Citation verification** | Free | **2–3 min per citation** | Dominates cost on long documents |
| Import resolution | Free | 5 min | Fully scriptable — automate it |
| Binoculars (local) | GPU or slow CPU | seconds/item | Free, private, no data leaves you |
| Commercial detectors | ~$0.01–0.10/doc **[V]** | seconds | Data leaves your control |
| Benford / GRIM | Free | 10 min | Needs the raw dataset |
| Problematic Paper Screener | Free | seconds | Public tool |
| Stylometric baseline | Free | 30–60 min | Needs prior samples from the author |
| Audio/video artifact review | Free–expensive | 30 min–hours | Poor return; do provenance first |

**Realistic totals:** a 4,000-word document with code takes about **1 hour** (v3 §12), and citation verification is most of it. **Automate import resolution and DOI checks** — they are the highest-yield checks and the most mechanisable. A 10-minute script pays for itself immediately.

**Rate limits:** free web verifiers are not built for bulk. For volume, use the APIs and respect their limits, or run local methods.

---

## 29. What this still does not cover

Stated plainly, so the next reader doesn't assume completeness. This is the pattern that produced v3's silent regression.

- **Live/streaming detection** — real-time video calls, live audio. Different problem, largely unsolved.
- **Multimodal cross-checks** — verifying that an image, its caption, and its metadata are mutually consistent.
- **Agentic artifacts** — traces left by browsing agents, RAG citation patterns, tool-use residue in outputs.
- **Non-Latin script forensics** — everything on stylometry here assumes Latin script. CJK, Arabic, Devanagari and Tamil have different tokenization behaviour and essentially no published detection curves.
- **Detecting AI *training data* contamination** — whether a model memorised a specific document.
- **Adversarial ML** — attacks on the detectors themselves beyond paraphrasing.
- **Hardware provenance** — C2PA at point of capture in cameras and phones; deployed but not covered here.
- **Blockchain/timestamping provenance** — an alternative approach, unassessed.
- **Insurance, procurement, and contractual angles** — AI-use warranties in supplier contracts.
- **Jurisdiction beyond the EU** — China's Sept 2025 visible-label rules are mentioned in v3; US state laws (California AB 602, Texas SB 751 and successors) and India's framework are not analysed.
- **Sector-specific regimes** — medical, financial, and legal filings have their own disclosure duties.

---

## 30. Consolidated index

| Need | Section |
|---|---|
| Is Claude's output watermarked? | v3 §1 |
| Evidence tiers E1–E5 | v3 §2 |
| C2PA / image provenance | v3 §3 · v4 §18 |
| Watermark mechanism and attacks | v3 §4 |
| Base rates and PPV | v3 §5 |
| Hybrid human/AI text | v3 §6 |
| Code | v3 §7 |
| Detectors, stylometry, Unicode | v3 §8 · v4 §23 |
| Chain of custody | v3 §9 |
| If you're accused | v3 §10 |
| Policy design | v3 §11 |
| Worked example, report template | v3 §12–13 |
| **Documents, PDF, Office** | **v4 §17** |
| **Generator-specific image metadata** | **v4 §18** |
| **Video** | **v4 §19** |
| **Audio, voice, music** | **v4 §20** |
| **Fabricated data, surveys** | **v4 §21** |
| **Academic publishing, paper mills** | **v4 §22** |
| **Measured detector FPRs (RAID)** | **v4 §23.1** |
| **Humanisers, evasion tells** | **v4 §24** |
| **Model-specific habits** | **v4 §25** |
| **Legal and privacy exposure** | **v4 §26** |
| **Decision flow** | **v4 §27** |
| **Costs and time** | **v4 §28** |

---

## Sources added in v4

**[P] Primary:**

- Hans et al., *Spotting LLMs With Binoculars*, ICML 2024 — https://arxiv.org/abs/2401.12070 · code https://github.com/ahans30/Binoculars
- Dugan et al., *RAID: A Shared Benchmark for Robust Evaluation of Machine-Generated Text Detectors* (FPR table) — https://arxiv.org/pdf/2405.07940
- *Echoes of Automation* (pre-GPT baseline + majority voting methodology) — https://arxiv.org/pdf/2508.06445
- Cabanac & Labbé, *The Problematic Paper Screener* — https://arxiv.org/pdf/2210.04895 · tool: https://www.irit.fr/~Guillaume.Cabanac/problematic-paper-screener
- *Detection of tortured phrases in scientific literature* — https://arxiv.org/pdf/2402.03370
- *RADAR Challenge 2026: Robust Audio Deepfake Recognition under Media Transformations* — https://arxiv.org/pdf/2605.09568
- *Investigating and preventing scientific misconduct using Benford's Law*, Research Integrity and Peer Review — https://researchintegrityjournal.biomedcentral.com/articles/10.1186/s41073-022-00126-w
- *Detecting academic fraud using Benford law: the case of Professor James Hunton* — https://www.sciencedirect.com/science/article/abs/pii/S0048733320301621
- Stanford Best Practices in Science — detecting survey data fabrication — https://bps.stanford.edu/home/statistical-forensics/statistical-forensics-techniques-detect-and-eliminate-fraud/techniques-0
- San Martín et al., *Proactive detection of voice cloning with localized watermarking* (AudioSeal), ICML 2024 — https://arxiv.org/abs/2401.17264

**[S] Secondary:**

- Chemistry World — *AI tools combat paper mill fraud* (7,500 tortured phrases; "surface region") — https://www.chemistryworld.com/features/ai-tools-tackle-paper-mill-fraud-overwhelming-peer-review/4022253.article
- C&EN — *Can we stop AI from flooding scientific journals?* (July 2026) — https://cen.acs.org/policy/publishing/ai-fraud-science-journal-generative-ai/104/web/2026/07
- The Conversation — *Problematic Paper Screener* — https://theconversation.com/problematic-paper-screener-trawling-for-fraud-in-the-scientific-literature-246317
- AI Safety Directory — *Deepfake Detection: Technologies, Tools & Best Practices (2026)* — https://aisecurityandsafety.org/en/guides/deepfake-detection/
- CASRAI — *Paper Mills & Tortured Phrases* — https://casrai.org/guides/paper-mills-and-tortured-phrases-research-integrity-red-flags

**[U] Unverified / preprint:**

- *The Watermark Shortcut: How Provenance Marking Sabotages Audio Deepfake Detection* — https://arxiv.org/pdf/2606.23335 (preprint; the claim is significant if it holds)
- Suno v5.5 Voices detection analysis — vendor-adjacent blog
- Pindrop / Resemble Detect / Hiya performance claims — vendor
- Midjourney C2PA status as of early 2026

---

## 31. Disclosure

Written by Claude (Opus 5), which per v3 §1 is not currently watermarked. Every claim carries a source grade. Code in §17.3 and §21.2 was written for this document; the `benford()` function is illustrative and its chi-square threshold assumes n ≥ 100 — validate before relying on it.

**Known limitation of this addendum:** §29 lists what it does not cover. That list exists because v3 dropped four modality sections without flagging it, and word count alone concealed the loss. If you extend this further, diff the section map, not the length.

---

## 32. Operational rules — turning forensics into practice

The rest of this document is about *detecting* AI involvement after the fact. This section is the inverse: standing rules that make AI-assisted work clean, checkable, and honestly attributed in the first place. Shipped as `CLAUDE.md` + `INSTALL.md` + `strip-ai-attribution` alongside this file.

### 32.1 Why the rules map onto the forensics

| Rule | Forensic basis |
|---|---|
| Verify every dependency exists | v3 §7.1 — phantom imports are the single strongest AI-code signal, and the slopsquatting attack surface |
| Never cite an unread source | v3 §0.1 — three false fabrication accusations in v2 came from exactly this |
| Mark uncertainty explicitly | v3 §0.4 source grading; unverifiable claims poison a report |
| XSS and log-injection focus | v4 §7.5 — measured ~15% and ~12% pass rates, flat across model generations |
| Comments explain *why* | v3 §7.6 — restating-the-code comments are a top behavioural indicator |
| No scaffolding in output | v3 §8.7 — leaked `contentReference` objects and `<think>` blocks are near-conclusive |
| Match repo style | v3 §7.6 — style discontinuity across files is a review trigger |
| Report honestly what ran | v3 §9 — chain of custody depends on accurate records of what was actually executed |
| No AI attribution in git | §32.2 below |

### 32.2 The attribution rule, and its honest limits

**What is controllable:** commit trailers, PR footers, session deep links. `Co-Authored-By: Claude`, `🤖 Generated with [Claude Code]`, `Claude-Session: https://claude.ai/code/session_…`.

**What is not:** the statistical text watermark. No opt-out exists. It is also close to irrelevant for code — v3 §4.3, entropy — and absent entirely from models released before 2 August 2026, which includes Opus 5.

**Anyone claiming to "remove the Claude watermark" by stripping Unicode is removing copy-paste artifacts (v3 §8.5), not a watermark.**

### 32.3 Why the enforcement layer has to be a git hook

This is the same principle as v3 §7.3, and it now has direct evidence behind it.

Multiple open issues on `anthropics/claude-code` report `includeCoAuthoredBy: false` and `attribution: {commit: "", pr: ""}` being ignored. Reported causes:

- The model re-adds the trailer when building a commit message manually via the Bash tool, bypassing the code path that reads the setting.
- The 