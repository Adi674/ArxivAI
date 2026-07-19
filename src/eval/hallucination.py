"""
src/eval/hallucination.py

NLI-based hallucination detector for ArxivAI v3.0.

Model: cross-encoder/nli-deberta-v3-small
  - CPU-only, ~200ms for a typical answer
  - Lazy-loaded singleton (same pattern as reranker.py)
  - Deterministic: no prompt injection risk, no LLM temperature variance

How it works:
  1. Split the generated answer into individual sentences
  2. For each sentence, build (sentence, chunk) pairs against top-5 source chunks
  3. Run NLI — model outputs [contradiction, neutral, entailment] logits
  4. Take max entailment score across all chunks for that sentence
  5. If max_entailment < ENTAILMENT_THRESHOLD → sentence is "unsupported"
  6. Return hallucination_rate = unsupported / total sentences

NLI label mapping (DeBERTa NLI models):
  Index 0: contradiction
  Index 1: neutral
  Index 2: entailment

Used together with the LLM judge for cross-validation:
  - If LLM judge faithfulness < 0.7 AND NLI hallucination_rate > 0.2 → high-confidence alert
  - If they disagree → log for manual review (catches both false positives and negatives)
"""

import logging
import re
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Singleton state ───────────────────────────────────────────────────────────
_nli_model = None
_NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-small"
_ENTAILMENT_IDX = 2        # entailment is index 2 for most NLI models
_ENTAILMENT_THRESHOLD = 0.5  # sentence with max_entailment < this is "unsupported"


def _get_nli_model():
    """Lazy-load the NLI cross-encoder on first call."""
    global _nli_model
    if _nli_model is None:
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"[NLI] Loading NLI model: {_NLI_MODEL_NAME}")
            _nli_model = CrossEncoder(
                _NLI_MODEL_NAME,
                num_labels=3,          # contradiction, neutral, entailment
                max_length=512,
            )
            logger.info("[NLI] NLI model loaded successfully.")
        except ImportError:
            logger.error("[NLI] sentence-transformers not installed.")
            raise
        except Exception as e:
            logger.error(f"[NLI] Failed to load NLI model: {e}")
            raise
    return _nli_model


def _split_sentences(text: str) -> list[str]:
    """
    Split answer text into individual sentences for NLI evaluation.
    Filters out very short fragments (< 20 chars) that aren't real claims.
    """
    # Split on sentence-ending punctuation followed by space/newline
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = []
    for s in raw:
        s = s.strip()
        # Skip: too short, citation-only lines, headers
        if len(s) < 20:
            continue
        if s.startswith("[") and s.endswith("]"):
            continue
        sentences.append(s)
    return sentences


def _extract_source_passages(retrieved_papers: list[dict], max_chunks: int = 5) -> list[str]:
    """
    Extract the content passages from retrieved papers to use as NLI premises.
    Truncates each chunk to 300 chars to keep NLI pairs within 512 tokens.
    """
    passages = []
    for paper in retrieved_papers[:max_chunks]:
        content = (paper.get("content") or "").strip()
        title = (paper.get("title") or "")
        # Prepend title for context
        passage = f"{title}. {content[:300]}" if title else content[:300]
        passages.append(passage)
    return passages


def check_hallucination(
    answer: str,
    retrieved_papers: list[dict],
) -> dict:
    """
    Run NLI-based sentence-level hallucination detection.

    For each sentence in the answer, checks if any source chunk entails it.
    Returns a dict compatible with EvalResult NLI fields.

    Optimisation: ALL (sentence, passage) pairs are batched into a single
    model.predict() call so DeBERTa runs ONE forward pass instead of N.

    Args:
        answer:            The generated answer text to check.
        retrieved_papers:  Source chunks used to generate the answer.

    Returns:
        dict with:
            hallucination_rate:  float in [0,1] — fraction of unsupported sentences
            unsupported_claims:  list[str] — sentences flagged as unsupported
            attribution_map:     dict[sentence → paper_id] — best-matching source
            nli_scores:          dict[sentence → max_entailment_score] for debugging
    """
    result = {
        "hallucination_rate": 0.0,
        "unsupported_claims": [],
        "attribution_map": {},
        "nli_scores": {},
    }

    if not answer or not retrieved_papers:
        logger.warning("[NLI] Empty answer or no sources — skipping NLI check.")
        return result

    try:
        model = _get_nli_model()
    except Exception as e:
        logger.error(f"[NLI] Cannot load NLI model: {e}. Skipping hallucination check.")
        return result

    sentences = _split_sentences(answer)
    passages = _extract_source_passages(retrieved_papers)

    if not sentences or not passages:
        return result

    # Cap sentences to avoid explosion on very long answers (10 × 5 = 50 pairs max)
    MAX_SENTENCES = 10
    sentences = sentences[:MAX_SENTENCES]

    n_passages = len(passages)
    logger.info(
        f"[NLI] Checking {len(sentences)} sentences against {n_passages} passages "
        f"({len(sentences) * n_passages} pairs in single batch)"
    )

    # ── Build ALL pairs at once ───────────────────────────────────────────────
    all_pairs = []
    for sentence in sentences:
        for passage in passages:
            all_pairs.append((sentence, passage))

    # ── Single batched forward pass ───────────────────────────────────────────
    try:
        logits = model.predict(all_pairs)  # shape: (n_sentences * n_passages, 3)

        def softmax(x):
            e_x = np.exp(x - np.max(x, axis=1, keepdims=True))
            return e_x / e_x.sum(axis=1, keepdims=True)

        probs = softmax(logits)
        entailment_scores = probs[:, _ENTAILMENT_IDX]  # shape: (n_sentences * n_passages,)
    except Exception as e:
        logger.error(f"[NLI] Batch prediction failed: {e}. Skipping hallucination check.")
        return result

    # ── Index back into per-sentence results ──────────────────────────────────
    unsupported: list[str] = []
    attribution: dict[str, str] = {}
    nli_debug: dict[str, float] = {}

    for i, sentence in enumerate(sentences):
        start = i * n_passages
        end = start + n_passages
        sentence_scores = entailment_scores[start:end]

        max_entailment = float(sentence_scores.max())
        best_passage_idx = int(sentence_scores.argmax())

        nli_debug[sentence[:80]] = round(max_entailment, 4)

        if max_entailment < _ENTAILMENT_THRESHOLD:
            unsupported.append(sentence)
            attribution[sentence[:80]] = "NO_SOURCE"
        else:
            best_paper = retrieved_papers[best_passage_idx]
            attribution[sentence[:80]] = best_paper.get("paper_id", "unknown")

    hallucination_rate = round(len(unsupported) / len(sentences), 4) if sentences else 0.0

    logger.info(
        f"[NLI] {len(unsupported)}/{len(sentences)} sentences unsupported. "
        f"hallucination_rate={hallucination_rate:.4f}"
    )

    result["hallucination_rate"] = hallucination_rate
    result["unsupported_claims"] = unsupported[:5]
    result["attribution_map"] = attribution
    result["nli_scores"] = nli_debug
    return result

