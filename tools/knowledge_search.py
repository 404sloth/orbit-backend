"""
Hybrid Knowledge Search Tool — Unified interface for SQL and RAG.
Searches structured project data and unstructured documents simultaneously.
"""
import json
from typing import Optional, List, Dict, Any
from langchain_core.tools import tool

from core.schemas import KnowledgeSearchSchema
from tools.sql import execute_read_query
from tools.rag import search_project_documents
from core.logger import logger

@tool(args_schema=KnowledgeSearchSchema)
def hybrid_knowledge_search(query: str, user_id: Optional[int] = None, role: str = "USER", depth: str = "balanced") -> str:
    """
    Performs a dual search across the SQL database and RAG document store.
    Use this for high-level queries like "What do we know about Project X?" 
    or "Find everything related to vendor Y".
    """
    if user_id is None:
        return json.dumps({"status": "error", "message": "user_id is required."})

    results = {
        "structured_data": [],
        "documents": [],
        "summary": ""
    }

    try:
        # 1. SQL Metadata Search (Projects, Vendors, Clients, Transcripts)
        # Search for projects
        sql_proj = f"SELECT 'Project' as type, project_name as name, current_status as info FROM projects WHERE project_name LIKE '%{query}%'"
        res_proj = json.loads(execute_read_query.invoke({"query": sql_proj, "user_id": user_id, "role": role}))
        if res_proj["status"] == "success":
            results["structured_data"].extend(res_proj["data"])

        # Search for transcripts (NEW)
        sql_trans = f"SELECT 'Transcript' as type, title as name, substr(raw_text, 1, 200) || '...' as info FROM meeting_transcripts WHERE raw_text LIKE '%{query}%' OR title LIKE '%{query}%'"
        res_trans = json.loads(execute_read_query.invoke({"query": sql_trans, "user_id": user_id, "role": role}))
        if res_trans["status"] == "success":
            results["structured_data"].extend(res_trans["data"])

        # 2. RAG Search
        if depth in ["balanced", "deep"]:
            rag_res_json = search_project_documents.invoke({"query": query, "user_id": user_id, "role": role, "scope": "global"})
            rag_res = json.loads(rag_res_json)
            if rag_res["status"] == "success":
                results["documents"].extend(rag_res["data"])
            
            # Also search personal/workspace if appropriate
            rag_res_personal_json = search_project_documents.invoke({"query": query, "user_id": user_id, "role": role, "scope": "personal"})
            rag_res_personal = json.loads(rag_res_personal_json)
            if rag_res_personal["status"] == "success":
                results["documents"].extend(rag_res_personal["data"])

        # Construct a combined message
        count_sql = len(results["structured_data"])
        count_rag = len(results["documents"])
        results["summary"] = f"Found {count_sql} database records and {count_rag} relevant document snippets."

        logger.info("Hybrid Knowledge Search completed", query=query, user_id=user_id, sql_count=count_sql, rag_count=count_rag)
        return json.dumps({
            "status": "success",
            "data": results,
            "message": results["summary"]
        })

    except Exception as e:
        logger.error(f"Hybrid Knowledge Search Error: {e}")
        return json.dumps({
            "status": "error",
            "message": f"Search failed: {str(e)}"
        })
