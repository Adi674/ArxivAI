"""
src/agents/intent_classifier.py

Agent 1: Intent Classifier.
Determines user query intent using llama-3.1-8b-instant (Groq) with conversation history context.
Classifies query into: research | conversational | clarification | out_of_scope.
"""

import json
import logging
from typing import List, Dict, Tuple, Optional
from sqlalchemy import select

from src.database import get_async_session_maker
from src.models import Message
from src.llm.provider import get_llm, call_llm

logger = logging.getLogger(__name__)

_INTENT_PROMPT = """You are an intent classifier for ArxivAI, an academic research assistant.
Given the user's current query and the recent conversation history, classify the intent into exactly ONE category:

Categories:
- research: The user is asking a research question, requesting papers, comparison, explanation of scientific concepts, or literature search.
- conversational: Greetings, thanks, simple acknowledgments ("hi", "hello", "thank you", "thanks", "ok", "yes", "cool").
- clarification: The user is asking for clarification of a previous answer or clarifying their own previous statement (e.g., "what did you mean by X?").
- out_of_scope: The user is asking about general weather, coding unrelated software, recipes, or topics completely unrelated to science.

Recent History:
{history}

Current Query: {query}

Respond ONLY with valid JSON:
{{"intent": "research", "confidence": 0.95, "reason": ""}}

JSON:"""


def _parse_intent_json(text: str) -> dict:
    """Parse intent JSON securely."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return {"intent": "research", "confidence": 0.5, "reason": "parsing_failed"}
        return json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"[IntentClassifier] JSON parsing failed: {e}. Raw: {text[:150]}")
        return {"intent": "research", "confidence": 0.5, "reason": "parsing_failed"}


async def classify_intent(
    query: str,
    conversation_id: Optional[str] = None,
    llm_mode: str = "balanced"
) -> Tuple[str, float]:
    """
    Classify the intent of the user query.
    Loads the last 5 messages from the database if conversation_id is provided.
    """
    history_str = "No recent history."
    
    # 1. Load history if available
    if conversation_id:
        try:
            session_maker = get_async_session_maker()
            async with session_maker() as db:
                stmt = (
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.desc())
                    .limit(5)
                )
                res = await db.execute(stmt)
                messages = res.scalars().all()
                
                # Format history chronologically (reverse the limit query results)
                msg_list = []
                for msg in reversed(messages):
                    role = "User" if msg.role == "user" else "Assistant"
                    msg_list.append(f"{role}: {msg.content[:150]}")
                if msg_list:
                    history_str = "\n".join(msg_list)
        except Exception as e:
            logger.warning(f"[IntentClassifier] Failed to load conversation history: {e}")

    # 2. Call safety/intent classifier
    try:
        llm = get_llm("intent_classifier", llm_mode)
        prompt = _INTENT_PROMPT.format(history=history_str, query=query)
        response_raw = call_llm(llm, prompt)
        intent_data = _parse_intent_json(response_raw)
    except Exception as e:
        logger.error(f"[IntentClassifier] LLM classification call failed: {e}")
        intent_data = {"intent": "research", "confidence": 0.9}

    intent = intent_data.get("intent", "research").strip().lower()
    confidence = float(intent_data.get("confidence", 0.5))
    
    # Validation fallback
    if intent not in ("research", "conversational", "clarification", "out_of_scope"):
        intent = "research"
        
    logger.info(f"[IntentClassifier] Classified intent as '{intent}' (confidence={confidence:.2f})")
    
    # Increment Prometheus metrics counter
    from src.eval.prometheus_metrics import INTENT_CLASSIFICATION_TOTAL
    INTENT_CLASSIFICATION_TOTAL.labels(intent=intent).inc()
    
    return intent, confidence
