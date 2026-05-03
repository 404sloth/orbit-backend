import os
from langchain_community.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma

# Ensure the DB directory exists
CHROMA_PERSIST_DIR = os.path.join(os.getcwd(), "chroma_db")

def get_vector_store() -> Chroma:
    """
    Initializes and returns the Chroma Vector Store using local Ollama embeddings.
    Ensure Ollama is running and `ollama pull nomic-embed-text` has been executed.
    """
    from core.config import settings
    
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text", 
        base_url=settings.ollama_base_url
    )
    
    return Chroma(
        collection_name="project_documents",
        embedding_function=embeddings,
        persist_directory=CHROMA_PERSIST_DIR
    )