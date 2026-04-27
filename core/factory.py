from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from core.config import settings




from langchain_core.runnables import Runnable

class SafeToolCallingLLM(Runnable):
    """
    A Runnable wrapper that handles bind_tools safely across primary and fallback LLMs.
    Ensures compatibility with LangChain's pipeline operator (|) and create_react_agent.
    """
    def __init__(self, primary_llm, fallback_llm):
        self.primary_llm = primary_llm
        self.fallback_llm = fallback_llm

    def bind_tools(self, tools, **kwargs):
        """Binds tools to primary and tries to bind to fallback."""
        p_with_tools = self.primary_llm.bind_tools(tools, **kwargs)
        try:
            f_with_tools = self.fallback_llm.bind_tools(tools, **kwargs)
            return p_with_tools.with_fallbacks([f_with_tools])
        except (NotImplementedError, AttributeError, TypeError):
            # Fallback doesn't support tools, return primary with tools only
            return p_with_tools

    def invoke(self, input, config=None, **kwargs):
        """Delegates invocation to the fallback chain."""
        chain = self.primary_llm.with_fallbacks([self.fallback_llm])
        return chain.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        """Delegates async invocation to the fallback chain."""
        chain = self.primary_llm.with_fallbacks([self.fallback_llm])
        return await chain.ainvoke(input, config=config, **kwargs)

    def __getattr__(self, name):
        """Delegate any other attributes (like model_name) to primary."""
        return getattr(self.primary_llm, name)


def get_llm(temperature: float = 0.0):
    """
    Returns a configured LLM based on environment settings.
    Primary: Groq or OpenAI
    Fallback: Ollama
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
    
    # 3. Return wrapped LLM for safe tool binding and Runnable compatibility
    return SafeToolCallingLLM(primary_llm, fallback_llm)