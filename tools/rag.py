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


@tool(args_schema=SearchDocumentsSchema)
def search_project_documents(query: str, top_k: int = 3, scope: str = "global", user_id: Optional[int] = None) -> str:
    """
    Searches the ChromaDB knowledge base for project documents,
    meeting transcripts, and RFPs using semantic similarity.
    Supports scoping for personal, workspace, or global documents.
    """
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
            
        docs = vector_store.similarity_search(query, k=k_val, filter=metadata_filter)

        if not docs:
            return json.dumps({
                "status": "success",
                "data": [],
                "message": f"No relevant documents found in {scope} scope."
            })

        results = [
            {
                "source": d.metadata.get("source", "Unknown"),
                "scope": d.metadata.get("scope", "global"),
                "content": d.page_content
            }
            for d in docs
        ]

        logger.info("RAG search completed", query=query, scope=scope, results_count=len(results))
        return json.dumps({
            "status": "success",
            "data": results,
            "message": f"Found {len(results)} relevant documents in {scope} scope."
        })
    except Exception as e:
        logger.error("RAG Search Error", error=str(e), query=query)
        return json.dumps({
            "status": "error",
            "data": None,
            "message": f"RAG search failed: {str(e)}"
        })


@tool(args_schema=AddDocumentsSchema)
def add_documents_to_knowledge_base(content: str, source: str, scope: str = "global", user_id: Optional[int] = None) -> str:
    """
    Ingests new documents into the ChromaDB vector knowledge base with metadata scoping.
    """
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