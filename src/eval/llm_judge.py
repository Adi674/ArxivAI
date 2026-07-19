"""
src/eval/llm_judge.py

7-Metric LLM-as-Judge evaluator for ArxivAI v3.0.

Design:
  - Runs 6 evaluation prompts in parallel (asyncio.gather)
  - Each metric evaluated independently — no self-bias from seeing other scores
  - Judge model is LARGER than the synthesizer model to reduce self-grading leniency
    (synthesizer: llama-3.1-70b-versatile | judge: llama-3.3-70b-versatile)
  - Each prompt returns JSON with: {score, evidence, feedback, reasoning}
  - Scores feed into EvalResult which computes weighted overall + refinement flag
  - combined_feedback goes directly into SYNTHESIS_REFINE_PROMPT
"""

import asyncio
import json
import logging
import time
from typing import Optional

from src.eval.metrics import EvalResult, DimensionScore

logger = logging.getLogger(__name__)

# ── Judge model — deliberately different from synthesizer to reduce self-bias ──
_JUDGE_MODEL_GROQ = "llama-3.3-70b-versatile"
_JUDGE_MODEL_FALLBACK = "llama-3.1-70b-versatile"

# ── Evaluation prompt templates ───────────────────────────────────────────────
# Each prompt asks the judge to reason step-by-step (chain-of-thought),
# quote evidence, give a numeric score, and write one feedback sentence.

_EVAL_PROMPTS: dict[str, str] = {

    "faithfulness": """You are an expert research evaluator. Assess the FAITHFULNESS of this answer.

FAITHFULNESS: Does every factual claim in the answer have explicit support from the source papers?
Score 1.0 = all claims fully supported | Score 0.0 = answer fabricates claims not in sources.

Question: {query}

Source papers (ground truth):
{sources}

Answer to evaluate:
{answer}

Step-by-step:
1. List each factual claim in the answer
2. For each claim, find the supporting sentence in the source papers (direct quote)
3. Flag any claim with NO supporting quote as hallucinated

Respond ONLY with valid JSON:
{{"score": 0.85, "evidence": "direct quote from source supporting your score", "feedback": "one actionable sentence for improvement", "reasoning": "brief chain-of-thought"}}

JSON:""",

    "answer_relevancy": """You are an expert research evaluator. Assess ANSWER RELEVANCY.

ANSWER RELEVANCY: Does the answer directly and completely address what was asked?
Score 1.0 = fully on-topic | Score 0.0 = answer ignores the question entirely.

Question: {query}

Answer to evaluate:
{answer}

Step-by-step:
1. Identify exactly what the question is asking (topic, scope, expected answer type)
2. Identify which parts of the answer are directly relevant
3. Identify any tangential or off-topic content

Respond ONLY with valid JSON:
{{"score": 0.85, "evidence": "quote from question or answer that supports your score", "feedback": "one actionable sentence for improvement", "reasoning": "brief chain-of-thought"}}

JSON:""",

    "context_recall": """You are an expert research evaluator. Assess CONTEXT RECALL.

CONTEXT RECALL: How much of the key information from the source papers is captured in the answer?
Score 1.0 = all important findings from sources are present | Score 0.0 = answer misses most of what sources say.

Question: {query}

Source papers (ground truth):
{sources}

Answer to evaluate:
{answer}

Step-by-step:
1. List the 3-5 most important findings in the source papers relevant to the question
2. Check which of those findings appear in the answer
3. Score based on fraction of important findings covered

Respond ONLY with valid JSON:
{{"score": 0.85, "evidence": "key finding from source that WAS or WAS NOT captured", "feedback": "one actionable sentence for improvement", "reasoning": "brief chain-of-thought"}}

JSON:""",

    "coherence": """You are an expert research evaluator. Assess COHERENCE.

COHERENCE: Is the answer logically structured, internally consistent, and easy to follow?
Score 1.0 = excellent logical flow | Score 0.0 = contradictory or incoherent.

Answer to evaluate:
{answer}

Step-by-step:
1. Check if the answer has a clear structure (intro → body → conclusion)
2. Check for internal contradictions
3. Check if transitions between ideas are logical

Respond ONLY with valid JSON:
{{"score": 0.85, "evidence": "quote from answer illustrating coherence or incoherence", "feedback": "one actionable sentence for improvement", "reasoning": "brief chain-of-thought"}}

JSON:""",

    "context_precision": """You are an expert research evaluator. Assess CONTEXT PRECISION.

CONTEXT PRECISION: Are the retrieved sources actually relevant to what was asked?
Score 1.0 = all sources are highly relevant | Score 0.0 = sources are off-topic noise.

Question: {query}

Source papers used:
{sources}

Step-by-step:
1. For each source, assess how relevant it is to the question
2. Count relevant vs irrelevant sources
3. Score = relevant / total

Respond ONLY with valid JSON:
{{"score": 0.85, "evidence": "source title that WAS or WAS NOT relevant", "feedback": "one actionable sentence for improvement", "reasoning": "brief chain-of-thought"}}

JSON:""",

    "citation_accuracy": """You are an expert research evaluator. Assess CITATION ACCURACY.

CITATION ACCURACY: Are all citations in the answer correct and verifiable against the source papers?
Score 1.0 = all citations exist and match claimed content | Score 0.0 = citations are fabricated or wrong.

Source papers available (these are the ONLY valid citations):
{sources}

Answer to evaluate:
{answer}

Step-by-step:
1. List every citation in the answer (e.g. [Author, Year] or [Paper Title])
2. Verify each citation exists in the available source papers
3. Verify the cited claim matches what the paper actually says

Respond ONLY with valid JSON:
{{"score": 0.85, "evidence": "specific citation that is correct or incorrect", "feedback": "one actionable sentence for improvement", "reasoning": "brief chain-of-thought"}}

JSON:""",
}


def _format_sources(retrieved_papers: list[dict]) -> str:
    """Format retrieved papers list into a concise source block for eval prompts."""
    lines = []
    for i, paper in enumerate(retrieved_papers[:5], start=1):
        title = paper.get("title", "Unknown")
        authors = paper.get("authors", "")
        content_preview = (paper.get("content") or "")[:300]
        lines.append(
            f"[{i}] {title} | {authors}\n"
            f"    Excerpt: {content_preview}..."
        )
    return "\n\n".join(lines)


def _parse_judge_response(response_text: str, metric: str) -> DimensionScore:
    """
    Parse judge LLM response into a DimensionScore.
    Robust to extra text around the JSON block.
    """
    try:
        # Extract JSON block — find first { and last }
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in judge response")

        data = json.loads(response_text[start:end])
        score = float(data.get("score", 0.5))
        score = max(0.0, min(1.0, score))  # clamp to [0,1]

        return DimensionScore(
            score=round(score, 4),
            evidence=str(data.get("evidence", ""))[:300],
            feedback=str(data.get("feedback", ""))[:200],
            reasoning=str(data.get("reasoning", ""))[:300],
        )

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"[LLMJudge] Failed to parse {metric} response: {e}. Defaulting to 0.5.")
        return DimensionScore(
            score=0.5,
            evidence="Parse error — judge response was malformed",
            feedback=f"Could not evaluate {metric} — manual review recommended",
            reasoning=response_text[:200],
        )


async def _score_dimension(
    groq_client,
    metric: str,
    prompt: str,
) -> tuple[str, DimensionScore]:
    """
    Call the judge LLM for a single metric.
    Returns (metric_name, DimensionScore).
    """
    try:
        response = groq_client.chat.completions.create(
            model=_JUDGE_MODEL_GROQ,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,   # low temperature — we want consistent scores
            max_tokens=400,
        )
        text = response.choices[0].message.content or ""
        return metric, _parse_judge_response(text, metric)

    except Exception as e:
        logger.error(f"[LLMJudge] {metric} evaluation failed: {e}")
        return metric, DimensionScore(
            score=0.5,
            feedback=f"Evaluation failed for {metric}: {str(e)[:100]}",
        )


async def evaluate(
    query: str,
    answer: str,
    retrieved_papers: list[dict],
    groq_client=None,
) -> EvalResult:
    """
    Run all 6 LLM judge evaluations in parallel and return a populated EvalResult.

    Args:
        query:            The original user query.
        answer:           The synthesized answer to evaluate.
        retrieved_papers: The paper chunks used to generate the answer.
        groq_client:      An initialised Groq client. If None, creates one.

    Returns:
        EvalResult with all dimension scores populated, overall_score computed,
        needs_refinement flag set, and combined_feedback ready for the refinement prompt.
    """
    if groq_client is None:
        from groq import Groq
        from src.config import get_settings
        settings = get_settings()
        groq_client = Groq(api_key=settings.GROQ_API_KEY)

    start_time = time.monotonic()
    sources_block = _format_sources(retrieved_papers)

    # Build prompts for all 6 metrics
    prompt_args = {
        "query": query,
        "answer": answer,
        "sources": sources_block,
    }

    tasks = []
    for metric, template in _EVAL_PROMPTS.items():
        filled_prompt = template.format(**{
            k: v for k, v in prompt_args.items()
            if f"{{{k}}}" in template
        })
        tasks.append(_score_dimension(groq_client, metric, filled_prompt))

    # Run all 6 evaluations in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    result = EvalResult()

    for item in results:
        if isinstance(item, Exception):
            logger.error(f"[LLMJudge] Dimension task raised exception: {item}")
            continue
        metric_name, dim_score = item
        setattr(result, metric_name, dim_score)

    # Compute weighted overall + set needs_refinement flag
    result.compute_overall()
    result.build_combined_feedback()

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    result.eval_latency_ms = elapsed_ms

    logger.info(
        f"[LLMJudge] Evaluation complete: overall={result.overall_score:.4f}, "
        f"needs_refinement={result.needs_refinement}, latency={elapsed_ms}ms"
    )
    return result
