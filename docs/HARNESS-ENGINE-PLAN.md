# Harness engine plan

Goal: a root-level engine that sets up every project on its own, keeps that setup current as the project changes, tracks the project's information, logs and decisions, and holds token use under a measured cap. Decisions inside the engine go through a local decision engine modelled on typed decision models such as Jev.

Status: this is the original design document, kept for the reasoning and the Jev comparison. It is not a description of what exists. `docs/ENGINE.md` is.

Built: project detection, the two setup modes, the triggers, generation and regeneration, the token caps and `harness doctor`, the decision engine in a reduced form (three flag questions, a local scorer, outcome labelling for two of them, calibration, bounded refits), the split of the global rules, and self-update of the install.

Not built, and described below as if planned: model backends (Haiku, Jev), the `score` and `choice` question types, cost fields on answers, expected-value gating, thresholds derived from outcomes, shadow mode, proposed diffs for rule text, retry or revert outcome signals, a `post-commit` trigger, and context selection or regeneration running through the decision engine (they use the loader's scoring and a change stamp). Model suggestions are not limited to conversation or subagent boundaries: a stronger model can be suggested on any prompt.

## Decided

- Projects, not folders. The engine acts on a project root: the nearest folder with a project marker (manifest, source tree, or `.git`). Git is not required.
- Skipped: the home folder itself, container folders that hold other projects (for example `~/Documents`), the excluded repos (the `sb_projects` set), and any project with a `.harness-skip` file.
- Runs by itself. Triggers: Claude Code session start, a `cd` hook in `~/.zshrc`, and git template hooks (`post-checkout` after clone, `post-commit`, `post-merge`). `harness init` remains a manual fallback only.
- A project without git gets the base setup at once. Stack-specific parts follow when manifests appear, and fieldbook memory follows when git appears.

## Confirmed

- Auto-update scope: generated blocks and numeric weights update automatically and are logged. Rule text and anything written by hand change only through a proposed diff.
- Memory: fieldbook, after its two open fixes are merged.
- Global rules: split into an always-loaded core (target about 1,500 tokens) and files loaded on demand.
- Model backends: none. The engine is local-only; the Haiku and Jev adapters are not built.

## 1. Decision engine

### Jev, in detail

What it is (TypeSafe docs): a hosted "System One" model. You send a `state` (text, JSON or images) and typed questions; it returns structured answers, never prose. Question types: Choice (`choice`, `probabilities`, `confidence`), Score (`score`, `probabilities`, `confidence`), Noul (a 0-1 probability that a statement is true) and Box (an image region). Questions in one request are answered in parallel and in isolation, so extra questions add little latency.

Confidence (TypeSafe docs): computed from the answer distribution, 1 when all probability sits on one option. The docs state it measures concentration, not the probability of being correct, make no calibration guarantee, and tell users to test thresholds on their own labelled data. Suggested starting points: below 0.5 escalate, above 0.9 before a destructive action, Noul between 0.3 and 0.7 treated as "unsure".

Documented patterns: speculative fan-out (many questions, filter in code), screen with a cheap yes/no first, a companion yes/no to detect "no option fits", routing by confidence, routing by probability with stricter thresholds for riskier actions, and composite scoring with weights you choose.

Measured results (secondary sources):

| Test | Jev | Comparison | Source |
|---|---|---|---|
| Vendor benchmark, scored against the average answer of two large models | 67.8%, $0.0004, 0.4 s per case | GPT-5.6 Terra 67.9%, Claude Opus 5 73.1% at 37.8 s | TypeSafe data via DataCamp and GreenNode |
| Phishing, one yes/no question, 2,000 emails | 62.6% | Claude Haiku 4.5 81.3% | Beri.net, independent |
| Same, five questions combined by a classifier trained on 1,000 labelled emails | 95.0% | Haiku 93.2% | Beri.net |
| 77-class routing | 78.8% | GPT-5.6 Terra 84.0% | AY Automate |
| Prompt-injection detection | 87.0%, best in that test | | AY Automate |
| Cascade: Jev first, escalate when unsure | matched Terra | at 26-28% of the cost, about half the latency | AY Automate |
| Keep only answers at confidence 0.90 or higher, 8-way routing | 83.8% to 95.5% accuracy | 70% of items kept | AY Automate |
| Latency through OpenRouter, 791 calls | median 0.33 s, slowest 1.42 s | | AY Automate |

Stated price: $0.042 per million input tokens, output free (vendor). Access: early access and waitlist, hosted only, no open weights, single region.

Known weaknesses: weak at counting, arithmetic and date comparison; reads literally and can miss negation; accuracy drops with long, noisy context; no reasons, only probabilities; can be steered by crafted input; a typed answer can still be the wrong option; thresholds must be chosen by the user ("delegates the hallucination problem a little bit to the user", Armin Ronacher).

Lessons from Jev-based routers for coding agents: switching the model mid-conversation invalidates the prompt cache, so several routers pin one model per conversation or vary only effort, and the better ones suggest rather than switch, with a confidence floor (for example 0.7).

### Gaps, and how ours fills them

| Gap in Jev | Ours |
|---|---|
| Stateless: judges only the state you send | Project-aware state built automatically: stack, memory bank, recorded decisions, session history, measured token use |
| Confidence is concentration, not correctness, and the user must calibrate | Calibrated from our own outcomes: every decision is logged and later matched with what happened, and the stated probability is corrected per question from the observed hit rate |
| Single-question accuracy is modest; the 95% result needed decomposition plus a trained combiner | Decomposition and a trained combiner are built in: each decision is several small signals combined by a per-question logistic model fitted on our logs |
| Thresholds set by hand | Thresholds derived per question from outcome data and the cost of being wrong versus the cost of escalating |
| No reasons | Every answer carries the signals that drove it; decisions can be replayed and audited |
| Weak at counting, arithmetic, dates, long context | Countable facts are computed in code (token counts, sizes, budgets, diffs, dates); a model backend only ever sees a short distilled state |
| No built-in "none of these" | Abstain is a valid answer on every question |
| Blind to token and cache cost; per-turn switching breaks the prompt cache | Cost-aware: the decision weighs measured tokens, cache invalidation and latency, and model changes are suggested at conversation start or subagent boundaries only |
| Hosted, networked, single region, data leaves the machine, waitlist | Local first: milliseconds, offline, no data egress, no cost; remote backends optional and off by default |
| Injectable through crafted input | The local backend scores structured features, not free text; no decision alone authorizes a risky action |

Where Jev stays better: understanding the meaning of free text (intent, nuanced classification) and image inputs. Local rules cannot match a trained model there. So ours escalates those questions, and only those, to a model backend when the local answer abstains: Jev if access is obtained, otherwise Haiku 5.5 with structured output.

"Better" is a claim to measure, not assume. The evaluation below compares ours, Haiku and Jev (if available) on our own logged decisions before any backend becomes the default.

### Design

Request: a `state` and named typed questions.

| Type | Answer |
|---|---|
| choice | option or `abstain`, probability per option, concentration, calibrated probability |
| score | level or `abstain`, distribution, concentration, calibrated probability |
| flag | probability true, with an unsure band |

Every answer also returns `reasons` (the top signals and their weights), `backend` and `cost` (tokens and milliseconds spent deciding).

Pipeline:

1. Signals: deterministic extractors turn the prompt, project and history into features (keyword and pattern hits, stack tags, file and token counts, recent outcomes). Computed in code, never guessed.
2. Local scorer: a per-question logistic model over the signals. It starts from hand-set weights and is refitted from logged outcomes. Python standard library only.
3. Calibration: map raw scores to observed hit rates by binning with smoothing, refreshed as outcomes arrive.
4. Abstain gate: below the per-question threshold, answer `abstain`, or escalate if a backend is enabled.
5. Escalation (optional): send a short distilled state to Jev or Haiku; combine with the local answer.
6. Act by expected value: probability of success times value, minus token, cache and latency cost. Risky actions need a high calibrated probability and confirmation.
7. Log the decision; attach the outcome later.

Outcome signals, read from transcripts and logs: the user switched models after a suggestion; Claude opened a file the pointer named; a task needed a retry or a stronger model; a regeneration was reverted.

Evaluation: replay logged decisions offline and report accuracy against outcomes, calibration error, abstain rate, and tokens saved, per backend. New logic runs in shadow mode (logged, not acted on) until it beats the current version.

Decisions moved onto the engine, in order of token value:

1. Context pointer: whether to add the paragraph at all. It fired on 238 of 530 prompts last month. Target: a stack change, the first prompt of a session, or a confident relevance shift.
2. Context selection: which rules, skills, agents and memory files fit the task, within the tier budget.
3. Model and effort for a conversation or subagent, cache-aware, replacing the keyword-only scorer.
4. Folder kind: project, container, home, or plain folder.
5. Regeneration: whether the project changed enough to regenerate.
6. Later: gating risky tool calls.

## 2. Token budget

Measured from real usage, not estimated.

- Baseline: the input tokens on the first turn of each session, read from Claude Code transcripts, broken down by source (global rules, project files, imported memory, skill and subagent descriptions, hook additions).
- Cap per session start, per tier, set in `config/harness-budgets.json`. `harness doctor` reports the breakdown and fails when a project exceeds the cap.
- Levers, largest first:
  - the global rules split (about 4,000 tokens loaded every session today)
  - fewer always-visible skill and subagent descriptions per project (pins and excludes chosen by the decision engine)
  - pointers instead of pasted content
  - the pointer gate from section 1
  - fieldbook pruning so memory stays bounded
- Every change is checked against the baseline before and after.

## 3. Automatic project setup

When a trigger fires in a project that has no setup yet:

1. Detect the stack (languages, frameworks, package manager), the real commands (build, test, lint, from `package.json` scripts, `Makefile`, `pyproject.toml` and similar), and existing conventions (lint and format configs).
2. Write a generated block into `AGENTS.md`: do's and don'ts compiled from the domain rules that match the stack, the commands, and pointers to memory. The block is capped in tokens. Tool stubs (`CLAUDE.md` and others) point at `AGENTS.md`.
3. Record the inputs used (a stamp of manifests, lockfiles, git and fieldbook) in `~/.ai-rules/data/projects/`, so a later trigger can tell whether anything changed. Optional overrides go in `.harness/config.json`.
4. With git: run fieldbook for the bank, task logs and decision records.
5. Log the setup in the engine change log.

When a trigger fires in a project that already has setup, the decision engine compares the input hashes. If the stack, commands or conventions changed, it regenerates only the generated blocks and logs what changed.

Guarantees: never overwrite hand-written text, never block a session or a commit, one run at a time per project.

## 4. Tracking

- Task logs and decisions: fieldbook (`.fieldbook/logs/hot/` per task, `04-decisions.md` for decision records, pruning into digests).
- Engine change log: every automatic setup, regeneration and weight change, with the reason.
- Agent rule in the generated block: record a decision when one is made, and check recorded decisions before contradicting one.
- Routing and decision logs: `~/.ai-rules/logs/`, without prompt text.

## 5. Self-updating loop

- ai-dotfiles itself: at session start, compare the installed version stamp with the repo, and re-install when the local repo is newer. Pulling from GitHub stays manual.
- Drift: `harness doctor` checks installed copies against the repo.
- Learning: a periodic review reads the decision and outcome logs. It retunes numeric weights and thresholds automatically, within bounds, and proposes rule text changes as a diff for approval.

## Phases

Each phase is tested and committed before the next.

0. Prerequisites: merge the two fieldbook fixes; measure the token baseline from existing transcripts.
1. Decision engine core: signals, local scorer, calibration, abstain, logging, shadow mode and the replay evaluation; move the context pointer and context selection onto it; `harness doctor` with the token breakdown and cap.
2. Automatic project setup: project detection, the three triggers, generation, the plain-folder-to-git upgrade, exclusions, regeneration on change.
3. Tracking: engine change log, agent decision rule, fieldbook integration checks.
4. Calibration and learning: outcome signals, per-question calibration, bounded auto-tuning, proposed rule diffs; optional model backends if approved.
5. Global rules split into core and on-demand files, if confirmed.

## Sources

- TypeSafe docs, Jev introduction: https://docs.typesafe.ai/introduction
- LangChain, harness with Jev (routing and tool gating middleware): https://www.langchain.com/blog/building-a-harness-with-jev
- Cluster, Route, Escalate (arXiv, June 2026): https://arxiv.org/abs/2606.27457
- Routing and cascades overview (RouteLLM, FrugalGPT figures, secondary): https://tianpan.co/blog/2025-11-03-llm-routing-model-cascades
- TypeSafe docs, Confidence: https://docs.typesafe.ai/confidence.md
- TypeSafe docs, Patterns: https://docs.typesafe.ai/patterns.md
- GreenNode, Jev benchmarks and limitations (vendor and independent figures): https://greennode.ai/blog/what-is-jev
- AY Automate, Jev use cases and caveats: https://www.ayautomate.com/blog/jev-use-cases
- Community Jev routers for coding agents: https://github.com/v-modal/awesome-jev-tools

Jev speed and cost multipliers are vendor-reported. No independent measurement of token savings in coding sessions was found.
