import os
# Disable ChromaDB telemetry to prevent 'capture()' argument errors
os.environ["ANONYMOUS_TELEMETRY"] = "False"

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    # LLM Provider: 'groq' or 'openai'
    llm_provider: str = "groq"
    
    # API Keys
    groq_api_key: str = ""
    openai_api_key: str = ""
    
    # Models
    groq_model: str = "llama-3.1-70b-versatile"
    openai_model: str = "gpt-4o"
    ollama_model: str = "llama3.1"
    
    # Fallback & Infrastructure
    ollama_base_url: str = "http://localhost:11434"

    # Database
    db_path: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "orbits.db")

    # LangSmith Tracing
    langchain_tracing_v2: str = "true"
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str = ""
    langchain_project: str = "executive_dashboard_mvp"

    # Safety limits
    sql_row_limit: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v.lower() not in ["groq", "openai"]:
            return "groq"
        return v.lower()

settings = Settings()

# Enable LangSmith tracing automatically if configured and key is present
if settings.langchain_tracing_v2 == "true" and settings.langchain_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
else:
    # Explicitly disable if configuration is incomplete to prevent log spam
    os.environ["LANGCHAIN_TRACING_V2"] = "false"