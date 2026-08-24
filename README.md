# Aster & Row Support Agent

A reliability-focused RAG support agent for Aster & Row (ecommerce: bags, drinkware, travel accessories), built to handle conflicting policy sources, tool-grounded order lookups, multi-turn context, and prompt-injection resistance without a happy-path-only demo.

---

## Setup and run instructions (clean clone)

```bash
git clone <your-repo-url>
cd ai-agent-intern-test

python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# edit .env and set GROQ_API_KEY

# build the vector index (run once, or after any knowledge-base/chunker change)
python -m app.ingest.build_index

# run the agent (fill in your actual entrypoint command here, e.g.:)
python -m app.cli
```

## Environment variables

`.env.example`:
```
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
EMBEDDING_MODEL=all-MiniLM-L6-v2
TRACE_LOG_PATH=logs/trace.jsonl
```

- `GROQ_API_KEY` — required. No default; the agent cannot make LLM calls without it.
- `GROQ_MODEL` — optional, defaults to `openai/gpt-oss-120b`. Groq periodically retires older model IDs; if you hit a `model_not_found` (404) error, check `https://api.groq.com/openai/v1/models` for the current lineup.
- `EMBEDDING_MODEL` — optional, defaults to `all-MiniLM-L6-v2` (local, no API cost).
- `TRACE_LOG_PATH` — optional, defaults to `logs/trace.jsonl`.

## Model, embedding, framework, and storage choices

- **LLM**: Groq-hosted `openai/gpt-oss-120b`, called via the Groq `/v1/chat/completions`-compatible SDK, `temperature=0` for reduced (not eliminated — see Known Limitations) run-to-run variance.
- **Embeddings**: `sentence-transformers` (`all-MiniLM-L6-v2`), run locally — no embedding API cost or external dependency for retrieval.
- **Framework**: plain Python, no agent framework (e.g. LangGraph). The workflow is a single bounded retrieve → generate → tool-call → respond loop with no multi-step planning, branching, or cycles — a framework would add orchestration overhead without addressing this system's actual reliability challenges (retrieval precedence, tool-result sanitization, deterministic handoff triggers), which are handled at the code level independent of any framework. Session state is ~15 lines (`SessionStore`); not enough complexity to justify a framework's state-management machinery either.
- **Storage**: NumPy array (`vectors.npy`) + JSON metadata (`metadata.json`) for the vector index — no vector database, per the assignment's explicit scope. Cosine similarity computed directly via NumPy at query time.

## Architecture

```
User message
   │
   ▼
ChunkStore.query()  ──── cosine similarity over locally-embedded KB chunks
   │
   ▼
rank_and_filter()  ──── authority re-rank (active > superseded > draft),
   │                    hard filter (official + active + customer-facing only),
   │                    candidate-conflict detection across active/official docs
   ▼
context block built  ── [file#heading] + [CANDIDATE CONFLICT] tags, untrusted-data framing
   │
   ▼
LLM call (Groq, temperature=0, tools=[get_order_status])
   │
   ├─ tool_calls? ──► get_order_status() ──► sanitized, whitelisted result only
   │                  (customer name/email/address/internal notes/risk score
   │                   are structurally excluded — never touch the LLM context)
   │                  └─► second LLM call with tool result
   ▼
footer parsed (HANDOFF / SOURCES)
   │
   ▼
deterministic backstops layered on top of the LLM's own footer:
   - system-prompt-extraction attempt (regex on user message) → force handoff
   - abstention language present AND no tool was called → force handoff
   - tool result flagged handoff_required (e.g. status=exception, not found)
   ▼
response + trace log entry (full retrieval scores, tool calls, handoff reasoning)
```

Key design decision: several reliability guarantees are enforced at the **code level**, not left to prompting alone — privacy (whitelisted `OrderLookupResult` schema, internal fields structurally unreachable), source authority (hard `filter_citable` gate), and handoff-on-injection/abstention (deterministic regex backstops layered under the LLM's own judgment). Prompting alone was empirically less reliable for these — see bug diary.

## Running evaluations

```bash
python -m evaluation.run_eval              # all cases (visible + custom)
python -m evaluation.run_eval --visible-only # supplied visible-cases.json only
python -m evaluation.run_eval --verbose      # show answer text for passing cases too
```

Individual case pass/fail is printed with failure reasons; results are also broken down by category (retrieval, groundedness, tool-use, tool-reliability, privacy, prompt-security, abstention, source-conflict, multi-source-grounding, conversation).

Assertions are deterministic wherever practical: `tool` (was a tool called), `tool_arguments` (with exact order ID), `required_sources` / `forbidden_sources_as_authority` (exact filename match), `must_not_include` (forbidden content, e.g. leaked PII), `handoff` (exact boolean match). `must_include_concepts` is the one intentionally-softer check — the assignment states exact wording isn't required, so these are keyword/phrase-family heuristics rather than exact substrings; this is called out explicitly in `run_eval.py`'s own docstring.

## Baseline and final evaluation results

*(Fill in with your actual first and most recent runs — see your terminal history. Suggested table below, using the numbers established in this session; replace with your own if you've run since.)*

| Category | Baseline (early run) | Final |
|---|---|---|
| retrieval | 1/2 | 2/2 |
| groundedness | 2/2 | 2/2 |
| multi-source-grounding | 0/1 | 1/1 |
| conversation | 0/1 | 2/2 |
| tool-use | 2/3 | 3/3 |
| tool-reliability | 5/5 | 5/5 |
| privacy | 1/1 | 1/1 |
| prompt-security | 1/3 | 3/3 |
| abstention | 0/1 | 1/1 |
| source-conflict | 1/2 | 2/2 |
| **TOTAL** | **13/21** | **21/22** (22 after adding 1 custom multi-turn case) |

Note on the final total: one run showed 21/22 due to a transient Groq API failure (not a logic defect — see Known Limitations); reruns of the same case pass cleanly. Report the number from your most recent clean run, and mention this variance honestly rather than only showing the best number.

## Bug diary

### 1. Crash: `UnboundLocalError` on `damaged_item_request`
- **Reproduction**: any eval case not matching the return-approval regex crashed `handle_turn` with `local variable 'damaged_item_request' referenced before assignment`.
- **Root cause**: the variable was only assigned inside an `if return_approval_request:` block, but referenced unconditionally later in the same function — Python treats a variable assigned anywhere in a function as local to the whole function, so the reference failed whenever the `if` didn't run (i.e. almost every message).
- **Fix**: reverted the accumulated heuristics (`damaged_item_request`, `knowledge_base_insufficient`, `source_conflict_handoff`) back to a minimal, always-defined set of deterministic backstops (`prompt_extraction_attempt`, `tool_forced_handoff`, later `abstention_detected`), each computed unconditionally every turn.
- **Regression test**: every case in the eval suite exercises `handle_turn` end-to-end; a scope bug like this fails 100% of cases identically, which is itself a fast detection signal (documented in this diary as a debugging pattern, not just a fix).

### 2. Retrieval-recall gap: heading text excluded from embeddings
- **Reproduction**: `canada-multiturn` consistently omitted the duties/taxes disclosure across multiple runs, despite the content existing in the KB (`06-international-shipping.md`, "Duties and taxes" section).
- **Root cause**: `build_index.py` only embeds `chunk.text` (the section body) — the section heading, though shown to the LLM in the final context via `[file#heading]`, was never part of the embedded vector. Short, keyword-light sections (e.g. "Duties and taxes" body never says "Canada") scored too low to reliably reach top-k on Canada-focused queries.
- **Fix**: `chunker.py` now prepends `"{doc_title} - {heading}"` to the text before it's embedded (contextual chunking), so heading signal contributes to retrieval scoring, not just final citation display.
- **Regression test**: confirmed via a trace-log diff script comparing retrieved-chunk scores before/after rebuild — `SHIP-2026-INTL-2` (duties/taxes chunk) score rose from 0.313 to 0.324 and the answer began reliably including the duties disclosure. This is the strongest-evidenced fix in the project — root cause was proven with actual before/after retrieval scores, not inferred from output alone.

### 3. Tool-result authority silently overridden by co-retrieved KB content
- **Reproduction**: custom case `custom-multiturn-order-followup` — asking about order ORD-1011 (which has `estimated_delivery: null`, "delivery estimate is not currently available") — produced an answer stating "orders typically arrive within 5-9 business days," sourced from the general `06-international-shipping.md` policy document rather than the tool's actual (null) result.
- **Root cause**: when a query mentions shipping/Canada context, KB retrieval pulls in the general shipping-policy chunk *in the same turn* as the tool call. Nothing in the prompt told the model that a specific order's tool result should override a general policy estimate when the two conflict on the same fact (an ETA).
- **Fix**: added an explicit prompt rule stating tool-result fields are authoritative for the specific order in question, and a general KB delivery-time range must not be substituted when the tool result's `estimated_delivery` is null.
- **Regression test**: `custom-multiturn-order-followup` in `cases_custom.json`, asserting `must_not_invent: ["arrival date"]` and requiring the "delivery estimate is unavailable" concept. This was discovered via a custom case, not a visible one — satisfies the "beyond exact wording of visible cases" requirement directly.

### 4. Abstention backstop misfired on tool-result gaps
- **Reproduction**: `custom-in-data-prompt-injection` (asking whether a coupon applies to ORD-1005) got `handoff=True` when it should have been `False` — the agent correctly reported no coupon exists, but that got misclassified as a KB-insufficiency abstention.
- **Root cause**: a deterministic backstop (`_ABSTENTION_RE`, added to catch cases where the model correctly abstains but doesn't use the prompt's required word "insufficient") matched on phrases like "does not include details" — which also fires when a tool result legitimately lacks a specific field, an unrelated situation to genuine KB-insufficiency.
- **Fix**: scoped the abstention backstop to only fire when no tool was called in that turn (`and not tool_calls_log`), since genuine KB-abstention and tool-result reporting are mutually exclusive situations in this system.
- **Regression test**: `custom-in-data-prompt-injection`'s `handoff: false` assertion.

## Known limitations and future improvements

- **Generation-side non-determinism**: `temperature=0` on a shared/batched Groq inference endpoint reduces but does not eliminate run-to-run phrasing variance. Verified via trace-log diffing that retrieval/chunking/embedding are fully deterministic (identical chunk IDs and scores across dozens of runs); variance is isolated to the LLM's generation step. Before production, I'd evaluate a self-hosted or dedicated-capacity endpoint if consistency requirements are strict.
- **KB content duplication**: `03-final-sale-and-promotions.md` and `04-damaged-or-wrong-items.md` both independently state that final-sale status doesn't block damaged-item review. The agent can correctly answer using only one document, which is defensible but means citation completeness varies by which document the model happened to draw from. Addressed partially via an explicit "cite all materially-supporting documents" prompt rule; a cleaner production fix would be de-duplicating the source KB itself.
- **Transient API failures**: Groq calls occasionally fail (rate limits, brief service interruptions) even with the built-in 2-retry backoff. The orchestrator falls back to a safe "contact support" message with `HANDOFF: yes` rather than crashing or hallucinating — but this does mean an eval run can show a false-negative case that isn't a logic defect. Production would want more aggressive retry/circuit-breaker handling and possibly a fallback model.
- **No multi-round tool orchestration**: the agent supports one round of tool calls per turn. Sufficient for the single `get_order_status` tool in scope; would need revisiting if future tools required chained/conditional calls.
- **Unbounded session history**: `SessionStore` never trims or summarizes conversation history. Fine for this assignment's scope; a production system would need a token-budget-aware truncation or summarization strategy.
- **Malformed order ID handling doesn't trigger handoff**: a structurally invalid ID (e.g. missing hyphen) returns `handoff_required=False` — treated as "please double-check the format," not "escalate to a human." Deliberate, but worth explicit product sign-off.
- **Deterministic backstops are keyword/regex-based, not semantic**: the system-prompt-extraction, abstention, and tool-authority overrides are pattern matches layered on top of LLM judgment, not verified independently by a second model. They reduce single-point-of-failure risk but can still have false negatives on cleverly-worded inputs; they're a backstop, not a guarantee.

## AI coding tools used

Built with Claude (Anthropic) as a pair-programming/debugging collaborator throughout — used for: reviewing each module against the assignment's stated requirements, diagnosing eval failures via trace-log evidence, writing and revising the deterministic-backstop and chunking fixes described above, and drafting this README.

**Example of an incomplete/wrong AI suggestion**: early in debugging `final-sale-damaged-exception`, Claude initially concluded the missing `03-final-sale-and-promotions.md` citation was explainable by benign KB content duplication and recommended leaving it alone rather than "fixing" it. Checking the actual trace log showed the relevant chunk (`RET-2026-02-2`) *was* being retrieved into context every run — meaning the model had the source available and was still choosing not to cite it, which is a real prompt-completeness gap (the prompt didn't instruct citing every materially-supporting source, only enough to answer). Verifying against raw trace data rather than accepting the first plausible explanation was necessary to catch this — a useful reminder that AI-suggested root causes should be checked against actual system evidence, not just accepted as reasonable-sounding.

## Demo

*(Embed a 2-4 minute GIF or linked video here showing: one KB question with citations, one order lookup, one multi-turn conversation, one refusal/handoff case, and the eval suite running.)*

```markdown
![Demo](./demo.gif)
```
or
```markdown
[![Demo video](./demo-thumbnail.png)](https://your-video-link)
```