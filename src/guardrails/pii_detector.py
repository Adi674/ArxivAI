"""
src/guardrails/pii_detector.py

PII (Personally Identifiable Information) detection and anonymisation.
Uses a fast regex engine for standard structural PII:
  - Email addresses
  - Phone numbers
  - Social Security Numbers (SSNs)
  - Credit card numbers
  - IP addresses

Design:
  - Sub-millisecond execution for all query lengths.
  - No external model downloads, no heavy NLP dependencies.
  - Replaces matches with placeholders: <EMAIL>, <PHONE_NUMBER>, <SSN>, etc.
  - Presidio is intentionally NOT used here — heavy spaCy models (400MB+)
    provide negligible benefit for an academic research assistant workload
    where structural PII (emails, phones, SSNs) is already caught by regex.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ── Regex Patterns ────────────────────────────────────────────────────────────
_PII_PATTERNS = {
    "EMAIL": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "PHONE_NUMBER": re.compile(
        r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


def anonymize_text(text: str) -> Tuple[str, bool]:
    """
    Scan text for PII patterns and replace them with anonymized placeholders.

    Args:
        text: The raw input text.

    Returns:
        Tuple of:
          - str:  The anonymized text (unchanged if no PII found).
          - bool: True if any PII was found and replaced.
    """
    if not text:
        return "", False

    anonymized = text
    pii_found = False

    for label, pattern in _PII_PATTERNS.items():
        if pattern.search(anonymized):
            pii_found = True
            anonymized = pattern.sub(f"<{label}>", anonymized)

    if pii_found:
        logger.warning("[PIIDetector] PII detected and anonymized in query.")

    return anonymized, pii_found
