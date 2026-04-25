from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama
from core.config import settings

def get_llm(temperature: float = 0.0):
    """
    Returns a primary LLM (Groq) for tool-based reasoning.
    Note: Fallbacks are disabled for agents using .bind_tools() until 
    fallback models (like ChatOllama) support the same interface.
    """
    primary_llm = ChatGroq(
        model=settings.primary_model,
        temperature=temperature,
        api_key=settings.groq_api_key,
        max_retries=2
    )
    
    # Fallback to Ollama is disabled for tool-using agents to prevent NotImplementedError
    # during .bind_tools() calls. 
    return primary_llm