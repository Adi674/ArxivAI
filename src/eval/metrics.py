"""
src/eval/metrics.py

Data structures for evaluation results.
Shared by LLM judge, NLI hallucination detector, and retrieval metrics.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DimensionScore:
    """
    Score for a single evaluation dimension from the LLM judge.

    Attributes:
        score:    Float in [0.0, 1.0] — the dimension score.
        evidence: Direct quote from source that supports or refutes this score.
        feedback: One-sentence actionable feedback for the refinement prompt.
        reasoning: Chain-of-thought reasoning from the judge LLM.
    """
    score: float
    evidence: str = ""
    feedback: str = ""
    reasoning: str = ""


@dataclass
class EvalResult:
    """
    Complete evaluation result for one RAG response.

    Weighted overall score formula:
        overall = Σ (weight_i × score_i)
        where weights sum to 1.0.

    Default weights (configurable):
        faithfulness:        0.25
        answer_relevancy:    0.20
        context_recall:      0.15
        coherence:           0.15
        context_precision:   0.15
        citation_accuracy:   0.10
    """
    # ── Per-dimension scores ──────────────────────────────────────────────────
    faithfulness: DimensionScore = field(default_factory=lambda: DimensionScore(score=0.0))
    answer_relevancy: DimensionScore = field(default_factory=lambda: DimensionScore(score=0.0))
    context_recall: DimensionScore = field(default_factory=lambda: DimensionScore(score=0.0))
    coherence: DimensionScore = field(default_factory=lambda: DimensionScore(score=0.0))
    context_precision: DimensionScore = field(default_factory=lambda: DimensionScore(score=0.0))
    citation_accuracy: DimensionScore = field(default_factory=lambda: DimensionScore(score=0.0))

    # ── NLI hallucination fields (from hallucination.py) ─────────────────────
    hallucination_rate: float = 0.0              # fraction of sentences flagged as unsupported
    unsupported_claims: list[str] = field(default_factory=list)    # flagged sentences
    attribution_map: dict[str, str] = field(default_factory=dict)  # sentence → best_paper_id

    # ── Aggregate ─────────────────────────────────────────────────────────────
    overall_score: float = 0.0                   # weighted average of 6 LLM dimensions
    needs_refinement: bool = False               # True if overall < threshold or any alert fires
    combined_feedback: str = ""                  # all feedbacks concatenated → SYNTHESIS_REFINE_PROMPT
    eval_latency_ms: int = 0                     # total evaluation wall time

    # Dimension weights
    WEIGHTS: dict = field(default_factory=lambda: {
        "faithfulness": 0.25,
        "answer_relevancy": 0.20,
        "context_recall": 0.15,
        "coherence": 0.15,
        "context_precision": 0.15,
        "citation_accuracy": 0.10,
    })

    # Alert thresholds — if any dimension score falls below its threshold, flag for refinement
    ALERT_THRESHOLDS: dict = field(default_factory=lambda: {
        "faithfulness": 0.70,
        "answer_relevancy": 0.65,
        "context_recall": 0.60,
        "coherence": 0.70,
        "context_precision": 0.50,
        "citation_accuracy": 0.80,
    })

    def compute_overall(self) -> None:
        """
        Compute weighted overall score and set needs_refinement flag.
        Call this after all dimension scores are populated.
        """
        weights = self.WEIGHTS
        thresholds = self.ALERT_THRESHOLDS

        scores = {
            "faithfulness": self.faithfulness.score,
            "answer_relevancy": self.answer_relevancy.score,
            "context_recall": self.context_recall.score,
            "coherence": self.coherence.score,
            "context_precision": self.context_precision.score,
            "citation_accuracy": self.citation_accuracy.score,
        }

        self.overall_score = round(
            sum(scores[dim] * weights[dim] for dim in weights), 4
        )

        # Flag refinement if any dimension is below its alert threshold
        # OR if overall score is below 0.65
        alert_fired = any(
            scores[dim] < thresholds[dim]
            for dim in thresholds
        )
        self.needs_refinement = alert_fired or self.overall_score < 0.65

        # Also flag if NLI hallucination rate is high
        if self.hallucination_rate > 0.20:
            self.needs_refinement = True

    def build_combined_feedback(self) -> str:
        """
        Concatenate all dimension feedbacks and NLI findings into a single
        actionable feedback string for the SYNTHESIS_REFINE_PROMPT.
        """
        parts: list[str] = []

        dim_map = {
            "Faithfulness": self.faithfulness,
            "Answer Relevancy": self.answer_relevancy,
            "Context Recall": self.context_recall,
            "Coherence": self.coherence,
            "Context Precision": self.context_precision,
            "Citation Accuracy": self.citation_accuracy,
        }

        for dim_name, dim in dim_map.items():
            if dim.feedback:
                parts.append(f"[{dim_name} {dim.score:.2f}] {dim.feedback}")

        if self.unsupported_claims:
            claims_text = " | ".join(self.unsupported_claims[:3])
            parts.append(
                f"[NLI Hallucination rate={self.hallucination_rate:.2f}] "
                f"Unsupported claims found: {claims_text}"
            )

        self.combined_feedback = "\n".join(parts)
        return self.combined_feedback

    def to_dict(self) -> dict:
        """Serialise to a plain dict for storage in RAGState."""
        return {
            "faithfulness": self.faithfulness.score,
            "answer_relevancy": self.answer_relevancy.score,
            "context_recall": self.context_recall.score,
            "coherence": self.coherence.score,
            "context_precision": self.context_precision.score,
            "citation_accuracy": self.citation_accuracy.score,
            "hallucination_rate": self.hallucination_rate,
            "overall_score": self.overall_score,
            "needs_refinement": self.needs_refinement,
            "eval_latency_ms": self.eval_latency_ms,
        }
