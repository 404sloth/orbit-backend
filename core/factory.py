from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama
from core.config import settings

def get_llm(temperature: float = 0.0):
    """
    Returns a primary LLM (Groq) with an Ollama fallback.
    If the primary provider goes down, it seamlessly routes to local deepseek-r1.
    """
    primary_llm = ChatGroq(
        model=settings.primary_model,  # e.g., "llama3-70b-8192" or "mixtral-8x7b-32768"
        temperature=temperature,
        api_key=settings.groq_api_key,
        max_retries=2
    )
    
    fallback_llm = ChatOllama(
        model=settings.fallback_model,
        base_url=settings.ollama_base_url,
        temperature=temperature
    )
    
    # Use fallbacks for resilience against network/API issues.
    # This will automatically switch to Ollama (deepseek-r1) if Groq is unreachable.
    return primary_llm.with_fallbacks([fallback_llm])