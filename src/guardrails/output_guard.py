"""
src/guardrails/output_guard.py

Output Guardrail Agent (Agent 8).
Validates the synthesized RAG answer before sending it to the user:
1. Citation Verification: Ensures all cited paper IDs exist in the retrieved papers list.
2. PII Anonymisation: Checks if any PII leaked into the output and anonymizes it.
3. Toxicity / Safety Check: Checks generated answer against safety criteria.
4. Token Limit: Truncates response if length exceeds token boundary.
"""

import json
import logging
import re
from typing import Tuple, List

from src.guardrails.pii_detector import anonymize_text
from src.llm.provider import get_llm, call_llm

logger = logging.getLogger(__name__)

_OUTPUT_SAFETY_PROMPT = """You are a safety evaluator for an academic research assistant.
Determine if the following generated answer contains harmful content, toxic statements,
or dangerous instructions.

Answer to evaluate:
{answer}

Respond ONLY with valid JSON:
{{"safe": true, "reason": ""}}

JSON:"""


def _parse_safety_json(text: str) -> dict:
    """Parse safety response."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return {"safe": True, "reason": ""}
        return json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"[OutputGuard] JSON parsing failed: {e}. Raw: {text[:150]}")
        return {"safe": True, "reason": ""}


def verify_citations(answer: str, retrieved_papers: List[dict]) -> Tuple[str, bool, List[str]]:
    """
    Scan final answer for bracketed citations like [paper_id] or [arXiv_id],
    and verify they exist in retrieved_papers. Removes citations that are hallucinated.
    
    Returns:
        Tuple of:
          - str: Cleaned answer with invalid citations removed/sanitized
          - bool: True if all citations matched retrieved papers, False if any were invalid
          - list[str]: List of invalid citation IDs detected
    """
    if not answer:
        return "", True, []
        
    valid_ids = {str(doc.get("paper_id")).lower() for doc in retrieved_papers}
    
    # Extract any brackets content: [2301.12345] or [vaswani_2017]
    citation_pattern = re.compile(r"\[([a-zA-Z0-9.\-_/:]+)\]")
    citations = citation_pattern.findall(answer)
    
    invalid_citations = []
    clean_answer = answer
    
    for citation in citations:
        citation_clean = citation.strip().lower()
        
        # Skip standard conversational terms inside brackets (if any)
        if citation_clean in ("yes", "no", "etc", "e.g", "i.e"):
            continue
            
        if citation_clean not in valid_ids:
            invalid_citations.append(citation)
            # Remove the invalid citation bracket from the final text
            clean_answer = clean_answer.replace(f"[{citation}]", "")
            
    # Clean up double spaces created by removal
    clean_answer = re.sub(r"\s+", " ", clean_answer).strip()
    
    verify_passed = len(invalid_citations) == 0
    if not verify_passed:
        logger.warning(f"[OutputGuard] Detected invalid/hallucinated citations: {invalid_citations}")
        
    return clean_answer, verify_passed, invalid_citations


async def run_output_guardrail(
    answer: str,
    retrieved_papers: List[dict],
    llm_mode: str = "balanced"
) -> Tuple[str, bool, str, bool, List[str]]:
    """
    Validate the synthesized answer.
    
    Returns:
        Tuple of:
          - str: Cleaned/anonymized answer
          - bool: allowed (True if answer is safe, False if blocked)
          - str: block_reason (empty string if allowed)
          - bool: citation_verify_passed (True if all citations exist in retrieved set)
          - list[str]: invalid_citations list
    """
    # ── Step 1: PII Anonymisation ────────────────────────────────────────────
    cleaned_answer, pii_found = anonymize_text(answer)
    
    # ── Step 2: Citation Verification ────────────────────────────────────────
    cleaned_answer, citation_verify_passed, invalid_citations = verify_citations(
        cleaned_answer, retrieved_papers
    )

    # ── Step 3: Toxicity / Output Safety Check ───────────────────────────────
    try:
        llm = get_llm("guardrail", llm_mode)
        prompt = _OUTPUT_SAFETY_PROMPT.format(answer=cleaned_answer)
        response_raw = call_llm(llm, prompt)
        safety_data = _parse_safety_json(response_raw)
    except Exception as e:
        logger.error(f"[OutputGuard] LLM safety check failed: {e}. Defaulting to safe.")
        safety_data = {"safe": True, "reason": ""}

    if not safety_data.get("safe", True):
        reason = safety_data.get("reason", "Answer contained unsafe content.")
        from src.eval.prometheus_metrics import GUARDRAIL_BLOCKS_TOTAL
        GUARDRAIL_BLOCKS_TOTAL.labels(guardrail_type="output", reason="toxic").inc()
        return "", False, f"Output blocked: {reason}", citation_verify_passed, invalid_citations

    # ── Step 4: Token Length Check ───────────────────────────────────────────
    # If the answer is extremely long (>20,000 characters), truncate it gracefully
    if len(cleaned_answer) > 20000:
        logger.warning(f"[OutputGuard] Answer length ({len(cleaned_answer)}) exceeds limit. Truncating.")
        cleaned_answer = cleaned_answer[:19900] + "... [Truncated by Output Guardrail due to length constraints]"

    return cleaned_answer, True, "", citation_verify_passed, invalid_citations
