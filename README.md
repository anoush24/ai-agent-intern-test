# Aster & Row Support Agent

A reliability-focused RAG support agent for Aster & Row (ecommerce: bags, drinkware, travel accessories). Built to handle the four failure modes named in the assignment brief — conflicting policy answers, invented order data, lost conversation context, and unsafe retrieved content — deliberately, not just on the happy path.

---

## 1. Setup and run instructions (clean clone)

```bash
git clone <your-repo-url>
cd ai-agent-intern-test

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# edit .env and set GROQ_API_KEY

# build the vector index (run once, or after any knowledge-base/chunker change)
python -m app.ingest.build_index

# run the agent
python run.py
```

## 2. Environment variables

`.env.example` (no real credentials committed):
```
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
EMBEDDING_MODEL=all-MiniLM-L6-v2
TRACE_LOG_PATH=logs/trace.jsonl
```

| Variable | Required | Default | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | No fallback; the agent cannot make LLM calls without it. |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | Groq periodically retires model IDs; check `api.groq.com/openai/v1/models` if you get a `model_not_found` error. |
| `EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Runs locally via `sentence-transformers`, no embedding API cost. |
| `TRACE_LOG_PATH` | No | `logs/trace.jsonl` | Structured per-turn observability log. |

## 3. Model, embedding, framework, storage

| Choice | What | Why |
|---|---|---|
| **LLM** | Groq-hosted `openai/gpt-oss-120b`, `temperature=0` | Low cost, tool-calling support; temp=0 minimizes (not eliminates) run-to-run phrasing variance. |
| **Embeddings** | `sentence-transformers` / `all-MiniLM-L6-v2`, local | No external embedding API, fully offline after first model download, deterministic. |
| **Framework** | Plain Python, no agent framework | The workflow is one bounded retrieve → generate → tool-call → respond loop, no branching/cycles — a framework (e.g. LangGraph) would add orchestration overhead without solving this system's actual reliability problems (retrieval precedence, tool sanitization, deterministic handoff), which are handled at the code level instead. |
| **Vector storage** | NumPy array + JSON metadata (`index/vectors.npy`, `index/metadata.json`) | No vector DB per assignment scope; cosine similarity computed directly at query time. |

## 4. Architecture

**Request flow:**

```
User message
   |
   v
[ retrieval/store.py ]
  ChunkStore.query() -- cosine similarity over
  locally-embedded KB chunks
   |
   v
[ retrieval/rank.py ]
  - authority re-rank (active > superseded > draft)
  - hard filter: official + active + customer-facing only
  - candidate-conflict detection across different
    active/official documents
   |
   v
[ agents/orchestrator.py ]
  builds [file#heading] + [CANDIDATE CONFLICT]
  tagged context block, untrusted-data framed
   |
   v
  Groq LLM call (temp=0, tools enabled)
   |
   +---------------------+
   | tool_calls present? |
   +----------+----------+
              |
     yes -----+----- no
      |               |
      v               v
[ tools/order_lookup.py ]   straight to answer
  whitelisted fields only --
  internal notes, email,
  address, risk score are
  structurally unreachable
      |
      v
  second LLM call with sanitized tool result
      |
      v
[ orchestrator.py -- footer parse + backstops ]
  - HANDOFF / SOURCES footer parsed from LLM
  - deterministic overrides layered on top:
      * system-prompt-extraction attempt (regex
        on user message)
      * abstention language + no tool called
      * tool result flagged handoff_required
        (e.g. status=exception, not found)
      |
      v
  response + full trace log entry
  (agents/session.py keeps per-session history;
   observability/tracer.py writes JSONL)
```

**Key design decision:** several guarantees are enforced in code, not left to prompting alone — privacy (whitelisted `OrderLookupResult` schema), source authority (hard `filter_citable` gate), and handoff-on-injection/abstention (deterministic regex backstops under the LLM's own judgment). Prompting alone was measurably less reliable for these — see bug diary.

### File map

| File | Role |
|---|---|
| `app/ingest/loader.py` | Parses KB markdown + YAML front matter into `Document` objects. |
| `app/ingest/chunker.py` | Splits documents by `##` heading; prepends doc title + heading to chunk text before embedding (contextual chunking — see bug diary #2). |
| `app/ingest/build_index.py` | Loads, chunks, embeds, and persists the full KB index. |
| `app/retrieval/embedder.py` | Wraps `sentence-transformers` for batch (index-build) and single-query embedding. |
| `app/retrieval/store.py` | NumPy-backed vector store; cosine similarity top-k query. |
| `app/retrieval/rank.py` | Authority re-ranking, citable-chunk filtering, candidate-conflict detection. |
| `app/tools/order_lookup.py` | Deterministic, side-effect-free order lookup; whitelist-only return schema — the sole module allowed to touch raw `orders.json`. |
| `app/agents/prompts.py` | System prompt: trust boundaries, citation rules, handoff triggers, worked examples. |
| `app/agents/session.py` | Per-session in-memory conversation history. |
| `app/agents/tool_schema.py` | OpenAI-style tool schema for `get_order_status`. |
| `app/agents/orchestrator.py` | Ties retrieval, LLM calls, tool execution, and deterministic handoff backstops together (`handle_turn`). |
| `app/observability/tracer.py` | Writes one structured JSONL trace event per turn. |
| `app/models/schemas.py` | Pydantic models: `Chunk`, `RetrievedChunk`, `OrderLookupResult`, `TraceEvent`, etc. |
| `evaluation/run_eval.py` | Deterministic + heuristic eval harness; category-level reporting. |
| `evaluation/cases_custom.json` | 6 original test cases beyond the supplied visible cases. |

## 5. Running evaluations

```bash
python -m evaluation.run_eval               # all cases (15 visible + custom)
python -m evaluation.run_eval --visible-only # supplied visible-cases.json only
python -m evaluation.run_eval --verbose      # show answer text for passing cases too
```

Assertions are deterministic wherever practical: `tool` / `tool_arguments` (exact tool call + order ID), `required_sources` / `forbidden_sources_as_authority` (exact filename match), `must_not_include` (forbidden content -- leaked PII, invented data), `handoff` (exact boolean). `must_include_concepts` is the one intentionally softer check, since the assignment states exact wording isn't required -- matched via phrase-family heuristics, documented as such in `run_eval.py`'s own docstring.

## 6. Baseline and final evaluation results

**Baseline** -- early integration run, before the deterministic-handoff backstops, chunking fix, and prompt refinements described in the bug diary:

| Category | Passed |
|---|---|
| retrieval | 0/2 |
| groundedness | 0/2 |
| multi-source-grounding | 0/1 |
| conversation | 0/1 |
| tool-use | 0/3 |
| tool-reliability | 0/5 |
| privacy | 1/1 |
| prompt-security | 0/3 |
| abstention | 0/1 |
| source-conflict | 0/2 |
| **TOTAL** | **1/21** |

*(This early run coincided with a scope bug -- see bug diary #1 -- causing nearly every turn to fail identically via the API-error fallback path, which is itself part of why that bug was easy to detect: a single root cause producing a near-total failure signature.)*

**Final** -- after all fixes below, run against all 15 supplied visible cases + all 6 original custom cases:

| Category | Passed |
|---|---|
| retrieval | 2/2 |
| groundedness | 2/2 |
| multi-source-grounding | 1/1 |
| conversation | 1/1 |
| tool-use | 3/3 |
| tool-reliability | 5/5 |
| privacy | 1/1 |
| prompt-security | 3/3 |
| abstention | 1/1 |
| source-conflict | 2/2 |
| **TOTAL** | **21/21** |

*(A 7th custom multi-turn case was added afterward and is not included in this total -- see Known Limitations for a note on generation-side variance across repeated runs.)*

## 7. Bug diary

### Bug 1 -- Crash: `UnboundLocalError` on a conditionally-assigned handoff variable
- **Reproduced by:** running the full eval suite; nearly every case failed identically via the generic "trouble reaching the support system" fallback.
- **Root cause:** a variable (`damaged_item_request`) was only assigned inside an `if return_approval_request:` block but referenced unconditionally later in the same function. Python treats any variable assigned anywhere in a function as local to the whole function, so the reference raised `UnboundLocalError` whenever that `if` didn't run -- i.e. almost every turn.
- **Fix:** reverted to a small set of always-defined, unconditionally-computed deterministic backstops (`prompt_extraction_attempt`, `tool_forced_handoff`, `abstention_detected`) rather than several conditionally-assigned heuristics layered on top of each other.
- **Regression test:** the full eval suite itself -- a scope bug like this produces a near-total, identically-shaped failure across every case, which made it fast to catch and characterize.

### Bug 2 -- Retrieval-recall gap: section headings excluded from embeddings
- **Reproduced by:** `canada-multiturn` consistently omitted the duties/taxes disclosure across multiple runs, despite the source content existing in the KB.
- **Root cause:** `build_index.py` only embedded `chunk.text` (the section body); the heading itself -- though shown to the LLM in the final citation -- was never part of the embedded vector. A short, keyword-light section (`## Duties and taxes`, body text never says "Canada") scored too low to reliably reach top-k on Canada-focused queries.
- **Fix:** `chunker.py` now prepends `"{doc_title} - {heading}"` to each chunk's text before embedding (contextual chunking).
- **Regression test:** confirmed via a trace-log score diff before/after rebuild -- the duties/taxes chunk's retrieval score rose from 0.313 to 0.324 and reliably entered the top-8 context afterward; the delivery answer began consistently including the duties disclosure.

### Bug 3 -- Tool-result authority silently overridden by co-retrieved KB content
- **Reproduced by:** a custom multi-turn case asking about a specific order with a null delivery estimate; the agent's answer stated a general "5-9 business days" range sourced from KB shipping policy instead of reporting the order's actual (unavailable) estimate.
- **Root cause:** when a query mentions shipping/Canada, KB retrieval pulls in the general shipping-policy chunk *in the same turn* as the order-lookup tool call. Nothing told the model that a specific order's tool result should take precedence over a general policy estimate when the two conflict on the same fact.
- **Fix:** added an explicit prompt rule stating tool-result fields are authoritative for the specific order in question, and a general KB delivery-time range must not be substituted when the tool's own estimate is null.
- **Regression test:** custom case asserting `must_not_invent: ["arrival date"]` and requiring the "delivery estimate is unavailable" concept -- discovered independently of the supplied visible cases.

### Bug 4 -- Deterministic abstention backstop misfired on tool-result gaps
- **Reproduced by:** a custom prompt-injection case (asking about a coupon on a specific order) was force-flagged `handoff=True` when it should have been `False` -- the agent correctly reported no coupon existed, but a keyword backstop misread that as a KB-insufficiency abstention.
- **Root cause:** the abstention backstop matched on phrases like "does not include details," which also fires when a tool result legitimately lacks one field -- an unrelated situation to genuine KB abstention.
- **Fix:** scoped the backstop to only fire when no tool was called that turn, since genuine KB-abstention and tool-result reporting are mutually exclusive in this system.
- **Regression test:** the custom case's `handoff: false` assertion.

## 8. Known limitations and planned improvements

- **Generation-side non-determinism.** `temperature=0` on a shared Groq endpoint reduces but doesn't eliminate phrasing variance between identical runs -- proven via trace-log diffing that retrieval/chunking/embedding are fully deterministic while generation isn't. *Improvement:* evaluate a dedicated-capacity or self-hosted endpoint if strict consistency is required in production.
- **KB content duplication.** Two documents (`03-final-sale-and-promotions.md`, `04-damaged-or-wrong-items.md`) both independently state the same final-sale/damage-review fact, so citation completeness can vary by which document the model draws from. *Improvement:* de-duplicate the source KB directly rather than relying on a prompt instruction to cite all supporting sources.
- **Transient API failures.** Groq calls occasionally fail even after 2 retries with backoff; the orchestrator falls back to a safe "contact support" message with forced handoff rather than crashing. *Improvement:* add a circuit breaker and/or a fallback model for production resilience.
- **Single-round tool calling.** No support for chained/conditional tool calls within one turn. *Improvement:* only needed if future tools require multi-step orchestration -- out of scope for the current single-tool design.
- **Unbounded session history.** `SessionStore` never trims or summarizes. *Improvement:* token-budget-aware truncation or summarization before production use with long-running conversations.
- **Malformed order IDs don't force handoff.** A structurally invalid ID (e.g. missing hyphen) is treated as "please recheck the format," not escalated. *Improvement:* explicit product sign-off on whether this should also trigger handoff.

## 9. AI coding tools used

Built with Claude (Anthropic) throughout, used for: reviewing each module against the assignment's stated requirements, diagnosing eval failures against real trace-log evidence rather than guesses, writing and revising the fixes described above, and drafting this README.

**Example of a wrong AI suggestion that was corrected through debate:** early on, when the `genuine-active-source-conflict` case's retrieved chunk-count grew from 5 to 8 after fixing conflict detection in `rank.py`, Claude's first hypothesis for a later vegan-question failure was that the same conflict-detection change was padding retrieval with irrelevant chunks (a shipping and a product-card chunk showing up for an unrelated materials question), and suggested raising the `min_score` threshold in `detect_conflict` to fix it. Before applying that, I pushed back and asked to actually check the retrieval scores rather than assume -- pulling the real trace-log scores showed the chunks were near the threshold but the deeper issue was unrelated to conflict detection at all. Continuing to investigate rather than accepting the first plausible explanation led to the real fix later (the heading-embedding gap in Bug 2), which had nothing to do with `min_score`. That exchange is why the workflow throughout this project was "verify against trace-log evidence before changing code," not "accept the first explanation" -- several proposed fixes were revised or rejected this way before landing on the actual root cause.

## 10. Demo

*(Embed a 2-4 minute GIF or linked video here, showing: one KB citation question, one order lookup, one multi-turn conversation, one abstention/handoff case, and the eval suite running.)*

```markdown
![Demo](./demo.gif)
```