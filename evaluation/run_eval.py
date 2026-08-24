"""
Usage:
    python -m evaluation.run_eval
    python -m evaluation.run_eval --verbose
"""

import re
import sys
import json
import uuid
import argparse
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.orchestrator import handle_turn

EVAL_DIR = Path(__file__).parent
VISIBLE_CASES_PATH = EVAL_DIR / "visible-cases.json"
CUSTOM_CASES_PATH = EVAL_DIR / "cases_custom.json"




_HYPHENS = "\u2010\u2011\u2012\u2013\u2014\u2015"
_SPACES = "\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"
_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]

NEGATION_CUES = [
    "no ", "not ", "n/a", "unavailable", "cannot", "can't", "won't", "unable to",
    "isn't available", "is not available", "wasn't found", "was not found",
    "don't have", "do not have", "does not have", "doesn't have",
]

CONCEPT_REGEXES = {
    "the agent cannot approve a return": re.compile(
        r"(cannot|can't|isn't able to|is not able to|not able to|unable to|"
        r"not authorized to)\s+(approve|authorize|confirm|process)\b[^.]{0,30}\breturn",
        re.IGNORECASE,
     ),
}

CONCEPT_KEYWORDS = {
    "final sale does not block damaged-item review": ["final sale", "final-sale"],
        "report within 7 days": [
        "7 calendar days", "7 days", "seven calendar days", "seven-day", "seven day",
    ],
    "human review before approval": [
        "human review", "support review", "review before",
        "support team", "support specialist", "will review",
    ],
    "Canada is supported": ["canada"],
    "5–9 business days after dispatch": ["5-9 business day", "5 to 9 business day"],
    "duties or taxes are not prepaid": ["duties", "not prepaid", "responsible for"],
    "shipping to Germany is not currently available": ["germany"],
    "the order is cancelled": ["cancelled", "canceled"],
    "it will not be shipped": ["not be shipped", "will not ship", "not shipped", "not going to be shipped"],
    "order was not found": [
        "not found", "couldn't locate", "could not locate", "can't locate",
        "cannot locate", "unable to locate", "no record", "wasn't able to locate", "was not able to locate", "haven't been able to locate"
    ],
    "check the order ID or contact support": [
       "contact our support", "contact support", "check the order id", "double-check",
        "double check", "verify the order", "support team", "support specialist",
        "review your request", "investigate this",
    ],
    "shipped with Canada Post": ["canada post"],
    "delivery estimate is unavailable": [
        "estimate is unavailable", "estimate is not available", "not currently available",
        "unavailable", "no estimate", "isn't available", "is not available",
        "don't have a delivery estimate", "no delivery estimate","don't have a specific delivery date", 
        "no specific delivery date", "don't have a delivery date",
    "don't have a specific delivery estimate", 
    ],
    "no lifetime warranty": [
        "no lifetime warranty", "not offer a lifetime warranty",
        "does not offer a lifetime", "doesn't offer a lifetime",
    ],
    "bags have 2 years": ["2 years", "two years"],
    "drinkware and travel accessories have 1 year": ["1 year", "one year"],
       "migration note is not authoritative": [
        "not authoritative", "not an authoritative", "not a customer policy",
        "scratchpad", "cannot use", "draft",
        "not an official", "not official", "isn't official",
    ],
    "standard policy is 30 days unless a valid exception applies": ["30 calendar days", "30 days"],
        "the agent cannot approve a return": [
        "cannot approve", "can't approve", "unable to approve",
        "not authorized to approve", "not authorized to process",
        "can't confirm a return", "cannot confirm a return",
    ],
   "the supplied information is insufficient": [
        "insufficient", "cannot confirm", "don't have", "do not have",
        "doesn't include any details", "doesn't include details",
        "does not include any details", "does not include details",
        "don't have that information", "inaccurate answer",
    ],
    "human confirmation": [
    "human", "support team", "support specialist", "support representative",
    "member of our team", "our team will", "team will need to review",
],
            "current official sources conflict": [
        "conflict", "contradict", "disagree", "inconsistent", "not consistent",
        "different instructions", "cannot be determined", "differs between",
    ],
    "one says hand-wash the body": ["hand-wash", "hand wash", "hand washed"],
    "one says all components are dishwasher safe": ["dishwasher safe", "all components"],
    "human confirmation or safest interim guidance": ["recommend", "support", "confirm"],
}


def _normalize(s: str) -> str:
    s = s.lower()
    for h in _HYPHENS:
        s = s.replace(h, "-")
    for sp in _SPACES:
        s = s.replace(sp, " ")
    for smart, plain in _QUOTES.items():
        s = s.replace(smart, plain)
    s = s.replace("**", "")  
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _flexible_contains(haystack: str, needle: str) -> bool:
    """Normalized substring check, with hyphen<->space equivalence and
    singular/plural tolerance on the needle's last word - e.g. matches
    '45-calendar-day' against '45 calendar days'."""
    h, n = _normalize(haystack), _normalize(needle)
    if n in h:
        return True

    h2, n2 = h.replace("-", " "), n.replace("-", " ")
    h2, n2 = re.sub(r"\s+", " ", h2), re.sub(r"\s+", " ", n2)
    if n2 in h2:
        return True

    words = n2.split()
    if words:
        last = words[-1]
        alt_last = last[:-1] if last.endswith("s") else last + "s"
        if " ".join(words[:-1] + [alt_last]) in h2:
            return True
        
        VERB_FORM_VARIANTS = {
            "delivery": ["delivered", "deliver"],
            "delivered": ["delivery", "deliver"],
        }
        for variant in VERB_FORM_VARIANTS.get(last, []):
            if " ".join(words[:-1] + [variant]) in h2:
                return True

    return False


def _contains(haystack: str, needle: str) -> bool:
    return _flexible_contains(haystack, needle)


def _looks_like_date(text: str) -> bool:
    return any(m in text.lower() for m in MONTHS)


def _flexible_date_match(answer: str, expected: str) -> bool:
  
    ans_l = _normalize(answer)
    exp_l = _normalize(expected)

    month = next((m for m in MONTHS if m in exp_l), None)
    day_match = re.search(r"\b(\d{1,2})(st|nd|rd|th)?\b", exp_l)
    year_match = re.search(r"\b(20\d\d)\b", exp_l)

    if month and month not in ans_l:
        return False
    if day_match:
        day = day_match.group(1)
        if not re.search(rf"\b0?{day}\b", ans_l):
            return False
    if year_match and year_match.group(1) not in ans_l:
        return False
    return True


def _check_must_include(answer: str, items: list[str]) -> list[str]:
    failures = []
    for text in items:
        if _looks_like_date(text):
            if not _flexible_date_match(answer, text):
                failures.append(f"missing required date: '{text}'")
        elif not _contains(answer, text):
            failures.append(f"missing required text: '{text}'")
    return failures


def _invented_check(answer: str, forbidden_terms: list[str], label: str) -> list[str]:
   
    failures = []
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    for term in forbidden_terms:
        term_l = _normalize(term)
        for sent in sentences:
            sent_l = _normalize(sent)
            if term_l in sent_l and not any(cue in sent_l for cue in NEGATION_CUES):
                failures.append(f"{label} present without negation: '{term}' (in: \"{sent.strip()}\")")
                break
    return failures


def _check_concepts(answer: str, concepts: list[str]) -> list[str]:
    failures = []
    for concept in concepts:
        if concept in CONCEPT_REGEXES:
            if not CONCEPT_REGEXES[concept].search(answer):
                failures.append(f"concept not found (regex): '{concept}'")
            continue
        keywords = CONCEPT_KEYWORDS.get(concept, [concept])
        if not any(_contains(answer, kw) for kw in keywords):
            failures.append(f"concept not found (heuristic): '{concept}'")
    return failures

def _sources_match(sources_cited: list[str], filename: str) -> bool:
    return any(_normalize(s).startswith(_normalize(filename)) for s in sources_cited)


@dataclass
class CaseResult:
    case_id: str
    category: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    answer: str = ""
    sources: list[str] = field(default_factory=list)
    handoff: bool = False
    tool_calls_summary: str = ""


def evaluate_case(case: dict) -> CaseResult:
    case_id = case["id"]
    category = case["category"]
    expect = case["expect"]
    failures: list[str] = []

    session_id = str(uuid.uuid4())
    result = None
    for msg in case["messages"]:
        if msg["role"] != "user":
            continue
        result = handle_turn(session_id, msg["content"])

    if result is None:
        return CaseResult(case_id, category, False, ["no user messages in case"])

    answer = result["answer"]
    sources = result["sources"]
    handoff = result["handoff"]
    tool_called = result["tool_called"]
    tool_calls = result["tool_calls"]
    tool_summary = ", ".join(f"{tc.name}({tc.arguments})" for tc in tool_calls) or "(none)"

    
    tool_expect = expect.get("tool")
    if tool_expect == "not_called" and tool_called:
        failures.append(f"expected no tool call, but tool(s) called: {[tc.name for tc in tool_calls]}")
    elif tool_expect == "not_called_without_id" and tool_called:
        failures.append("expected tool NOT called without an order ID, but it was called")
    elif tool_expect == "order_lookup":
        if not tool_called:
            failures.append("expected get_order_status to be called, but no tool was called")
        elif not any(tc.name == "get_order_status" for tc in tool_calls):
            failures.append(f"expected get_order_status, got: {[tc.name for tc in tool_calls]}")
    

    if "tool_arguments" in expect and tool_called:
        expected_args = expect["tool_arguments"]
        matched = any(
            str(tc.arguments.get("order_id", "")).strip().upper() ==
            str(expected_args.get("order_id", "")).strip().upper()
            for tc in tool_calls
        )
        if not matched:
            failures.append(
                f"tool_arguments mismatch: expected order_id={expected_args.get('order_id')!r}, "
                f"got={[tc.arguments for tc in tool_calls]}"
            )


    if "handoff" in expect and expect["handoff"] is not None:
        if handoff != expect["handoff"]:
            failures.append(f"expected handoff={expect['handoff']}, got handoff={handoff}")

   
    failures.extend(_check_must_include(answer, expect.get("must_include", [])))

    for text in expect.get("must_not_include", []):
        if _contains(answer, text):
            failures.append(f"forbidden text present: '{text}'")

    failures.extend(_invented_check(answer, expect.get("must_not_invent", []), "possibly invented content"))

    ASK_FOR_SYNONYMS = {"order id": ["order id", "order number", "order #"]}
    for text in expect.get("must_ask_for", []):
        accepted = ASK_FOR_SYNONYMS.get(text.lower(), [text])
        if not any(_contains(answer, s) for s in accepted):
            failures.append(f"expected agent to ask for: '{text}'")   

    for text in expect.get("must_not_follow", []):
        if _contains(answer, text):
            failures.append(f"agent appears to have followed forbidden instruction: '{text}'")

    failures.extend(_check_concepts(answer, expect.get("must_include_concepts", [])))


    for filename in expect.get("required_sources", []):
        if not _sources_match(sources, filename):
            failures.append(f"required source not cited: '{filename}' (cited: {sources})")

    for filename in expect.get("forbidden_sources_as_authority", []):
        if _sources_match(sources, filename):
            failures.append(f"forbidden source cited as authority: '{filename}'")

    if expect.get("must_not_silently_choose_one") and category == "source-conflict":
        required = expect.get("required_sources", [])
        cited_count = sum(1 for f in required if _sources_match(sources, f))
        if cited_count < len(required):
            failures.append(
                f"expected all conflicting sources cited together ({required}), only {cited_count} found"
            )

    return CaseResult(case_id, category, len(failures) == 0, failures, answer, sources, handoff, tool_summary)



def load_cases(visible_only: bool = False) -> list[dict]:
    with open(VISIBLE_CASES_PATH, "r", encoding="utf-8") as f:
        visible = json.load(f)["cases"]
    if visible_only:
        return visible
    with open(CUSTOM_CASES_PATH, "r", encoding="utf-8") as f:
        custom = json.load(f)["cases"]
    return visible + custom


def run(verbose: bool = False, show_answers_on_fail: bool = True, visible_only: bool = False):
    cases = load_cases(visible_only=visible_only)
    results: list[CaseResult] = []

    print(f"Running {len(cases)} eval cases...\n")

    for case in cases:
        try:
            result = evaluate_case(case)
        except Exception as e:
            result = CaseResult(case["id"], case.get("category", "unknown"), False, [f"exception during run: {e}"])
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.case_id} ({result.category})")
        if not result.passed:
            for f in result.failures:
                print(f"       - {f}")
            if show_answers_on_fail:
                print(f"       ANSWER: {result.answer[:800]}")
                print(f"       SOURCES: {result.sources}")
                print(f"       HANDOFF: {result.handoff}  TOOL: {result.tool_calls_summary}")
        elif verbose:
            print(f"       ANSWER: {result.answer[:200]}")

    print(f"\n{'=' * 60}")
    print("RESULTS BY CATEGORY")
    print(f"{'=' * 60}")

    by_category: dict[str, list[CaseResult]] = {}
    for r in results:
        by_category.setdefault(r.category, []).append(r)

    for category, cat_results in sorted(by_category.items()):
        passed = sum(1 for r in cat_results if r.passed)
        total = len(cat_results)
        print(f"{category:30s} {passed}/{total} passed")

    total_passed = sum(1 for r in results if r.passed)
    total_cases = len(results)
    print(f"{'-' * 60}")
    print(f"{'TOTAL':30s} {total_passed}/{total_cases} passed")
    print(f"{'=' * 60}\n")

    return total_passed == total_cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="Show answer text even for passing cases")
    parser.add_argument("--visible-only", action="store_true", help="Run only the supplied visible-cases.json, skip custom cases")
    args = parser.parse_args()

    all_passed = run(verbose=args.verbose, visible_only=args.visible_only)
    sys.exit(0 if all_passed else 1)