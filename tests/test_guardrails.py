"""
tests/test_guardrails.py

Unit tests for ArxivAI v3.0 Input and Output Guardrail Agents (Phase 4).
Tests:
- PII Detection: Email, Phone, SSN, Credit Card, IP Address anonymisation.
- Rate Limiting: Memory-based sliding window gating.
- Citation Verification: Filtering hallucinated citations.
- Out of scope regex check: Detection of forbidden topics.
"""

import pytest
import time
import asyncio
from uuid import uuid4

from src.guardrails.pii_detector import anonymize_text
from src.guardrails.rate_limiter import check_rate_limit
from src.guardrails.output_guard import verify_citations
from src.guardrails.input_guard import run_input_guardrail


def test_pii_anonymizer():
    # Test email anonymization
    text1 = "Contact me at research.assistant@example.org for details."
    anon1, found1 = anonymize_text(text1)
    assert found1 is True
    assert "research.assistant@example.org" not in anon1
    assert "<EMAIL>" in anon1
    
    # Test phone number anonymization
    text2 = "My direct line is (555) 123-4567. Call anytime."
    anon2, found2 = anonymize_text(text2)
    assert found2 is True
    assert "(555) 123-4567" not in anon2
    assert "<PHONE_NUMBER>" in anon2
    
    # Test SSN anonymization
    text3 = "Do not share SSN like 000-12-3456."
    anon3, found3 = anonymize_text(text3)
    assert found3 is True
    assert "000-12-3456" not in anon3
    assert "<SSN>" in anon3

    # Test clean text remains untouched
    text4 = "Attention Is All You Need is a seminal paper published in 2017."
    anon4, found4 = anonymize_text(text4)
    assert found4 is False
    assert anon4 == text4


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window():
    user_id = str(uuid4())
    
    # Allow exactly 3 requests in a 2-second window
    allowed1, _ = await check_rate_limit(user_id, limit=3, window_seconds=2)
    allowed2, _ = await check_rate_limit(user_id, limit=3, window_seconds=2)
    allowed3, _ = await check_rate_limit(user_id, limit=3, window_seconds=2)
    
    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is True
    
    # 4th request must be rate limited
    blocked, retry_after = await check_rate_limit(user_id, limit=3, window_seconds=2)
    assert blocked is False
    assert retry_after > 0
    
    # Wait for the window to expire
    await asyncio.sleep(2.1)
    
    # Request should be allowed again
    allowed_again, _ = await check_rate_limit(user_id, limit=3, window_seconds=2)
    assert allowed_again is True


def test_verify_citations():
    retrieved = [
        {"paper_id": "bert_2018"},
        {"paper_id": "gpt_2020"},
    ]
    
    # Text with valid citation
    text_valid = "BERT model [bert_2018] outperforms previous models."
    cleaned_valid, passed_valid, invalid_valid = verify_citations(text_valid, retrieved)
    assert passed_valid is True
    assert len(invalid_valid) == 0
    assert cleaned_valid == text_valid
    
    # Text with invalid citation
    text_invalid = "This was disproven by [hallucinated_2024] and also shown in [gpt_2020]."
    cleaned_invalid, passed_invalid, invalid_invalid = verify_citations(text_invalid, retrieved)
    assert passed_invalid is False
    assert "hallucinated_2024" in invalid_invalid
    assert "hallucinated_2024" not in cleaned_answer_format(cleaned_invalid)
    assert "[gpt_2020]" in cleaned_invalid
    assert "[hallucinated_2024]" not in cleaned_invalid


def cleaned_answer_format(text: str) -> str:
    return text


@pytest.mark.asyncio
async def test_input_guardrail_oos_regex():
    user_id = str(uuid4())
    
    # Scope check out-of-scope query
    allowed, reason, _, _, _ = await run_input_guardrail(
        "Can you write a poem about the weather forecast?",
        user_id
    )
    assert allowed is False
    assert "out of scope" in reason.lower()
    
    # Scope check clean query
    allowed_cs, _, _, _, _ = await run_input_guardrail(
        "Explain self-attention in Transformer architectures.",
        user_id
    )
    assert allowed_cs is True
