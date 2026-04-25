"""
RAG Tools for the Project Knowledge Agent.
Provides semantic document search and ingestion into ChromaDB.
"""
import json
from langchain_core.tools import tool
from langchain_core.documents import Document

from core.schemas import SearchDocumentsSchema, AddDocumentsSchema
from db.vector import get_vector_store
from core.logger import logger
from core.exceptions import RetrievalError


@tool(args_schema=SearchDocumentsSchema)
def search_project_documents(query: str, top_k: int = 3) -> str:
    """
    Searches the ChromaDB knowledge base for project documents,
    meeting transcripts, and RFPs using semantic similarity.

    Input:
        query: A natural language search string.
        top_k: Max number of document chunks to return (default 3).

    Output:
        A JSON object with status and a list of matching documents,
        each containing 'source' metadata and 'content' text.

    Always use this tool FIRST when answering questions about
    meetings, requirements, vendor proposals, or project context.
    """
    try:
        vector_store = get_vector_store()
        
        # Robust integer conversion for Groq compatibility
        try:
            k_val = int(top_k) if top_k is not None else 3
        except (ValueError, TypeError):
            k_val = 3
            
        docs = vector_store.similarity_search(query, k=k_val)

        if not docs:
            return json.dumps({
                "status": "success",
                "data": [],
                "message": "No relevant documents found for your query."
            })

        results = [
            {
                "source": d.metadata.get("source", "Unknown"),
                "content": d.page_content
            }
            for d in docs
        ]

        logger.info("RAG search completed", query=query, results_count=len(results))
        return json.dumps({
            "status": "success",
            "data": results,
            "message": f"Found {len(results)} relevant documents."
        })
    except Exception as e:
        logger.error("RAG Search Error", error=str(e), query=query)
        return json.dumps({
            "status": "error",
            "data": None,
            "message": f"RAG search failed: {str(e)}"
        })


@tool(args_schema=AddDocumentsSchema)
def add_documents_to_knowledge_base(content: str, source: str) -> str:
    """
    Ingests new documents into the ChromaDB vector knowledge base.

    Input:
        content: The text content to embed and store (meeting notes,
                 requirements, transcripts, etc.).
        source: A descriptive label like 'Meeting Transcript - April 12'.

    Output:
        A JSON object confirming successful ingestion with source and length.

    Use this when the user provides new unstructured text data
    that should be saved for later retrieval.
    """
    try:
        vector_store = get_vector_store()
        doc = Document(
            page_content=content,
            metadata={"source": source}
        )
        vector_store.add_documents([doc])
        logger.info("RAG Ingestion Successful", source=source, length=len(content))
        return json.dumps({
            "status": "success",
            "data": {"source": source, "length": len(content)},
            "message": f"Ingested document '{source}' ({len(content)} chars)."
        })
    except Exception as e:
        logger.error("RAG Ingestion Error", error=str(e), source=source)
        return json.dumps({
            "status": "error",
            "data": None,
            "message": f"Ingestion failed: {str(e)}"
        })