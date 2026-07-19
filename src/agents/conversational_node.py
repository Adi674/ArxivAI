"""
src/agents/conversational_node.py

Agent 9: Conversational Agent.
Handles conversational, greetings, thanks, or simple clarifications directly with a single LLM call.
Bypasses the expensive 7-agent RAG search pipeline to reduce latency and token costs.
"""

import logging
from sqlalchemy import select
from typing import Optional

from src.database import get_async_session_maker
from src.models import Message
from src.llm.provider import get_llm, call_llm

logger = logging.getLogger(__name__)

_CONVO_SYSTEM_PROMPT = """You are ArxivAI, a helpful academic research assistant.
You are having a direct conversational exchange (greetings, feedback, or follow-up clarification).
Be polite, concise, and helpful.

Recent History:
{history}

User: {query}
Assistant:"""


async def run_conversational_response(
    query: str,
    conversation_id: Optional[str] = None,
    llm_mode: str = "balanced"
) -> str:
    """
    Generate a direct conversational response without RAG search.
    Loads recent conversation turns for context.
    """
    history_str = "No recent history."
    
    if conversation_id:
        try:
            session_maker = get_async_session_maker()
            async with session_maker() as db:
                stmt = (
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.desc())
                    .limit(6)
                )
                res = await db.execute(stmt)
                messages = res.scalars().all()
                
                msg_list = []
                for msg in reversed(messages):
                    role = "User" if msg.role == "user" else "Assistant"
                    msg_list.append(f"{role}: {msg.content[:200]}")
                if msg_list:
                    history_str = "\n".join(msg_list)
        except Exception as e:
            logger.warning(f"[ConvoAgent] Failed to load history: {e}")
            
    try:
        llm = get_llm("synthesizer", llm_mode)
        prompt = _CONVO_SYSTEM_PROMPT.format(history=history_str, query=query)
        response = call_llm(llm, prompt)
        return response.strip()
    except Exception as e:
        logger.error(f"[ConvoAgent] Failed to generate conversational response: {e}")
        return "I'm here to help. How can I assist you with your research today?"
