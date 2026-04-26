from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from core.config import settings

def get_llm(temperature: float = 0.0):
    """
    Returns a configured LLM based on environment settings.
    Primary: Groq or OpenAI
    Fallback: Ollama (always attached)
    """
    # 1. Initialize Primary Provider
    if settings.llm_provider == "openai":
        primary_llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=temperature,
            api_key=settings.openai_api_key,
        )
    else:
        # Default to Groq
        primary_llm = ChatGroq(
            model=settings.groq_model,
            temperature=temperature,
            api_key=settings.groq_api_key,
            max_retries=2
        )
    
    # 2. Initialize Fallback (Ollama)
    fallback_llm = ChatOllama(
        model=settings.ollama_model,
        temperature=temperature,
        base_url=settings.ollama_base_url,
    )
    
    # 3. Attach fallback logic
    # Note: Using .with_fallbacks allows the chain to recover if primary API fails
    return primary_llm.with_fallbacks([fallback_llm])