# src/llm/provider.py
import logging
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Agent → model hint (used by providers that support model selection)
AGENT_MODELS = {
    "domain_classifier": "llama3-8b-8192",
    "query_analyzer":    "llama3-8b-8192",
    "search_strategy":   "llama3-8b-8192",
    "retriever":         "llama3-8b-8192",
    "reasoner":          "llama3-70b-8192",
    "synthesis":         "llama3-70b-8192",
    "evaluator":         "llama3-8b-8192",
}

# mode → provider preference order (no Ollama, no Anthropic)
MODE_PROVIDERS = {
    "budget":   ["groq"],
    "balanced": ["groq", "openrouter"],
    "quality":  ["groq", "openrouter", "gemini"],
    "research": ["groq", "openrouter", "gemini"],
}


def get_llm(agent_name: str, mode: str = "balanced"):
    """
    Return the correct LangChain LLM for the given agent and mode.
    Tries providers in fallback order until one works.

    Args:
        agent_name: One of the 7 agent names
        mode: budget | balanced | quality | research

    Returns:
        A LangChain-compatible LLM/ChatModel instance

    Raises:
        RuntimeError: If all providers fail (no API keys set)
    """
    model_name = AGENT_MODELS.get(agent_name, "llama3-8b-8192")
    providers = MODE_PROVIDERS.get(mode, ["groq", "openrouter"])

    for provider in providers:
        llm = _try_provider(provider, model_name, agent_name)
        if llm:
            return llm

    raise RuntimeError(
        f"All LLM providers failed for agent '{agent_name}'. "
        "Set at least GROQ_API_KEY in your .env file."
    )


def _try_provider(provider: str, model_name: str, agent_name: str):
    """
    Try to instantiate a provider's LLM. Returns None on failure.

    Args:
        provider: Provider name string
        model_name: Model identifier
        agent_name: Agent name (for logging only)

    Returns:
        LLM instance or None
    """
    try:
        if provider == "groq" and settings.GROQ_API_KEY:
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                api_key=settings.GROQ_API_KEY,
                model_name=model_name,
                temperature=0.1,
            )
            logger.info(f"[{agent_name}] Using Groq ({model_name})")
            return llm

        elif provider == "openrouter" and settings.OPENROUTER_API_KEY:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
                model="mistralai/mistral-7b-instruct",
                temperature=0.1,
            )
            logger.info(f"[{agent_name}] Using OpenRouter")
            return llm

        elif provider == "gemini" and settings.GEMINI_API_KEY:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                google_api_key=settings.GEMINI_API_KEY,
                model="gemini-1.5-flash",
                temperature=0.1,
            )
            logger.info(f"[{agent_name}] Using Gemini")
            return llm

    except Exception as e:
        logger.warning(f"[{agent_name}] Provider '{provider}' failed: {e}")
        return None

    return None


def call_llm(llm, prompt: str) -> str:
    """
    Call the LLM with a prompt string. Returns text response.
    Handles both ChatModel (message output) and plain LLM (string output).

    Args:
        llm: LangChain LLM or ChatModel instance
        prompt: Prompt string to send

    Returns:
        Response text as string

    Raises:
        Exception: Re-raises if LLM call fails
    """
    try:
        response = llm.invoke(prompt)
        if hasattr(response, "content"):
            return response.content.strip()
        return str(response).strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise