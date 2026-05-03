"""
RAG Tools for the Project Knowledge Agent.
Provides semantic document search and ingestion into ChromaDB.
"""
import json
from typing import Optional
from langchain_core.tools import tool
from langchain_core.documents import Document

from core.schemas import SearchDocumentsSchema, AddDocumentsSchema
from db.vector import get_vector_store
from core.logger import logger
from core.exceptions import RetrievalError


from langchain_core.runnables import RunnableConfig

@tool(args_schema=SearchDocumentsSchema)
def search_project_documents(query: str, config: RunnableConfig, top_k: int = 3, scope: str = "global", user_id: Optional[int] = None, role: str = "USER") -> str:
    """
    Searches the ChromaDB knowledge base for project documents,
    meeting transcripts, and RFPs using semantic similarity.
    Uses config to automatically retrieve user context if not provided.
    """
    # Prefer values from config if available
    cfg_user_id = config.get("configurable", {}).get("user_id")
    actual_user_id = user_id if user_id is not None else cfg_user_id
    user_id = actual_user_id
    try:
        vector_store = get_vector_store()
        
        # Robust integer conversion
        try:
            k_val = int(top_k) if top_k is not None else 3
        except (ValueError, TypeError):
            k_val = 3

        # Build strict security filter using ChromaDB logical operators
        if scope == "personal":
            if not user_id:
                return json.dumps({"status": "error", "message": "User ID required for personal scope."})
            
            metadata_filter = {
                "$and": [
                    {"user_id": {"$eq": user_id}},
                    {"scope": {"$eq": "personal"}}
                ]
            }
        elif scope == "workspace":
            if not user_id:
                return json.dumps({"status": "error", "message": "User ID required for workspace scope."})
            
            metadata_filter = {
                "$and": [
                    {"user_id": {"$eq": user_id}},
                    {"scope": {"$eq": "workspace"}}
                ]
            }
        else: # Default to global
            metadata_filter = {"scope": {"$eq": "global"}}
            
        # Use MMR for more diverse results
        docs = vector_store.max_marginal_relevance_search(query, k=k_val, fetch_k=k_val*3, filter=metadata_filter)

        if not docs:
            return json.dumps({
                "status": "success",
                "data": [],
                "message": f"No relevant documents found in {scope} scope."
            })

        # Format results compactly
        formatted_lines = []
        for i, d in enumerate(docs, 1):
            source = d.metadata.get("source", "Unknown")
            scope = d.metadata.get("scope", "global")
            # Explicitly format the citation tag so the agent learns to use it
            formatted_lines.append(f"[Document {i} | Source: {source} | Scope: {scope}]\n{d.page_content}\n")
        
        result_str = "\n".join(formatted_lines)

        logger.info("RAG search completed", query=query, scope=scope, results_count=len(docs))
        return json.dumps({
            "status": "success",
            "data": result_str,
            "message": f"Found {len(docs)} diverse relevant documents in {scope} scope."
        })
    except Exception as e:
        logger.error("RAG Search Error", error=str(e), query=query)
        return json.dumps({
            "status": "error",
            "data": None,
            "message": f"RAG search failed: {str(e)}"
        })


@tool(args_schema=AddDocumentsSchema)
def add_documents_to_knowledge_base(content: str, source: str, config: RunnableConfig, scope: str = "global", user_id: Optional[int] = None, role: str = "USER") -> str:
    """
    Ingests new documents into the ChromaDB vector knowledge base with metadata scoping.
    Uses config to automatically retrieve user context if not provided.
    """
    cfg_user_id = config.get("configurable", {}).get("user_id")
    actual_user_id = user_id if user_id is not None else cfg_user_id
    user_id = actual_user_id
    try:
        vector_store = get_vector_store()
        metadata = {
            "source": source,
            "scope": scope,
        }
        if user_id:
            metadata["user_id"] = user_id
            
        doc = Document(
            page_content=content,
            metadata=metadata
        )
        vector_store.add_documents([doc])
        logger.info("RAG Ingestion Successful", source=source, scope=scope, user_id=user_id)
        return json.dumps({
            "status": "success",
            "data": {"source": source, "scope": scope, "length": len(content)},
            "message": f"Ingested document '{source}' into {scope} scope."
        })
    except Exception as e:
        logger.exception("RAG Ingestion Failed", source=source)
        return json.dumps({
            "status": "error",
            "data": None,
            "message": f"Ingestion failed: {str(e)}"
        })