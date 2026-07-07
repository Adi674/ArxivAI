import logging
from functools import lru_cache
from src.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Agent → preferred model mapping
AGENT_MODELS = {
    "domain_classifier": "mistral",
    "query_analyzer":    "mistral",
    "search_strategy":   "mistral",
    "retriever":         "neural-chat",
    "reasoner":          "llama2:13b",
    "synthesis":         "llama2:13b",
    "evaluator":         "llama2",
}

# mode → provider preference
MODE_PROVIDERS = {
    "budget":   ["ollama"],
    "balanced": ["ollama", "groq"],
    "quality":  ["ollama", "groq", "openrouter"],
    "research": ["ollama", "groq", "openrouter", "gemini", "anthropic"],
}


def get_llm(agent_name: str, mode: str = "balanced"):
    """
    Return the correct LangChain LLM for the given agent and mode.
    Tries providers in fallback order until one works.
    """
    model_name = AGENT_MODELS.get(agent_name, "mistral")
    providers = MODE_PROVIDERS.get(mode, ["ollama", "groq"])

    for provider in providers:
        llm = _try_provider(provider, model_name, agent_name)
        if llm:
            return llm

    raise RuntimeError(f"All LLM providers failed for agent: {agent_name}")


def _try_provider(provider: str, model_name: str, agent_name: str):
    """Try to instantiate a provider's LLM. Returns None on failure."""
    try:
        if provider == "ollama":
            from langchain_community.llms import Ollama
            llm = Ollama(base_url=settings.OLLAMA_BASE_URL, model=model_name)
            logger.info(f"[{agent_name}] Using Ollama ({model_name})")
            return llm

        elif provider == "groq" and settings.GROQ_API_KEY:
            from langchain_groq import ChatGroq
            llm = ChatGroq(api_key=settings.GROQ_API_KEY, model_name="llama3-8b-8192")
            logger.info(f"[{agent_name}] Using Groq fallback")
            return llm

        elif provider == "openrouter" and settings.OPENROUTER_API_KEY:
            from langchain_community.llms import OpenAI
            llm = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.OPENROUTER_API_KEY,
                model="mistralai/mistral-7b-instruct",
            )
            logger.info(f"[{agent_name}] Using OpenRouter fallback")
            return llm

        elif provider == "gemini" and settings.GEMINI_API_KEY:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                google_api_key=settings.GEMINI_API_KEY,
                model="gemini-pro",
            )
            logger.info(f"[{agent_name}] Using Gemini fallback")
            return llm

        elif provider == "anthropic" and settings.ANTHROPIC_API_KEY:
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                model="claude-3-haiku-20240307",
            )
            logger.info(f"[{agent_name}] Using Anthropic fallback")
            return llm

    except Exception as e:
        logger.warning(f"[{agent_name}] Provider '{provider}' failed: {e}")
        return None

    return None


def call_llm(llm, prompt: str) -> str:
    """
    Call the LLM with a prompt string. Returns text response.
    Handles both LLM (string output) and ChatModel (message output).
    """
    try:
        response = llm.invoke(prompt)
        if hasattr(response, "content"):
            return response.content.strip()
        return str(response).strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise