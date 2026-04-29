"""
Centralized Pydantic schemas for all Orbit tools.
Provides strict type validation and rich descriptions for LLM tool binding.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


# ========================== SQL Tool Schemas ==========================

class ExecuteQuerySchema(BaseModel):
    """Schema for the execute_read_query tool."""
    query: str = Field(
        description=(
            "A single SQL SELECT statement to execute against the project database. "
            "Must use explicit column names (never SELECT *). "
            "Use JOINs for multi-table queries and WHERE for filtering."
        )
    )
    user_id: Optional[int] = Field(
        None,
        description="The ID of the user performing the query. Automatically injected, do not provide manually."
    )

class CacheMetricSchema(BaseModel):
    """Schema for the cache_dashboard_metric tool."""
    metric_key: str = Field(
        description="Unique identifier for the dashboard metric (e.g., 'alpha_milestone_risk')."
    )
    status: str = Field(
        description="The evaluated status: 'At Risk', 'On Track', 'Delayed', 'Completed', or 'Critical'."
    )
    reason: str = Field(
        description="A brief explanation justifying the assigned status."
    )

class ListTablesSchema(BaseModel):
    """Schema for the list_database_tables tool."""
    pass  # No input required

class DescribeTableSchema(BaseModel):
    """Schema for the describe_table_schema tool."""
    table_name: str = Field(
        description="The exact name of the database table to describe (e.g., 'projects', 'milestones')."
    )


# ========================== RAG Tool Schemas ==========================

class SearchDocumentsSchema(BaseModel):
    """Schema for the search_project_documents tool."""
    query: str = Field(
        description="A semantic search query to find relevant project documents, transcripts, or requirements."
    )
    top_k: Optional[Any] = Field(
        default=3,
        description="Maximum number of relevant document chunks to return. MUST be an integer between 1 and 10. If a string is provided, it will be converted."
    )
    scope: Optional[str] = Field(
        default="global",
        description="The scope of the search: 'global', 'workspace', or 'personal'."
    )
    user_id: Optional[int] = Field(
        None,
        description="The ID of the user performing the search (optional, used for personal scope)."
    )

class AddDocumentsSchema(BaseModel):
    """Schema for the add_documents_to_knowledge_base tool."""
    content: str = Field(
        description="The text content to ingest into the vector database (meeting notes, requirements, etc.)."
    )
    source: str = Field(
        description="Descriptive source label for the document (e.g., 'Meeting Transcript - April 12')."
    )
    scope: str = Field(
        default="global",
        description="The scope of the document: 'global', 'workspace', or 'personal'."
    )
    user_id: Optional[int] = Field(
        None,
        description="The ID of the user who owns the document (required for personal scope)."
    )

class KnowledgeSearchSchema(BaseModel):
    """Schema for the hybrid_knowledge_search tool."""
    query: str = Field(
        description="A natural language query to search both structured project data (SQL) and unstructured documents (RAG)."
    )
    user_id: Optional[int] = Field(
        None,
        description="The ID of the current user. Automatically injected."
    )
    depth: str = Field(
        default="balanced",
        description="Search depth: 'fast' (metadata only), 'balanced' (metadata + RAG), or 'deep' (full SQL + RAG)."
    )


class SearchTranscriptsSchema(BaseModel):
    """Schema for the search_meeting_transcripts tool."""
    query: str = Field(
        description="A name, topic, or keyword to search for within meeting transcripts."
    )
    user_id: Optional[int] = Field(
        None,
        description="The ID of the current user. Automatically injected."
    )
class GenerateReportSchema(BaseModel):
    """Schema for the generate_executive_report tool."""
    doc_type: str = Field(
        description="Type of document to generate: 'Meeting Summary', 'RFP', 'SOW', or 'Project Brief'."
    )
    title: str = Field(
        description="The primary title of the document (e.g., 'Project Phoenix Status Report')."
    )
    subtitle: Optional[str] = Field(
        None,
        description="A secondary subtitle or date range."
    )
    content_markdown: str = Field(
        description="The full content of the document in Markdown format. Use headings (#) for sections."
    )
    format: str = Field(
        default="PDF",
        description="The output format of the report. Must be one of ['PDF', 'DOCX', 'EXCEL']."
    )

# ========================== API Schemas ==========================

class ChatRequest(BaseModel):
    """Incoming chat request from the React frontend."""
    prompt: str = Field(..., description="The user's text prompt or question to the AI assistant.")
    thread_id: Optional[str] = Field(None, description="Unique identifier for the chat thread. If omitted, a new thread will be created.")

class ChatResponse(BaseModel):
    """Outgoing chat response to the React frontend."""
    thread_id: str = Field(..., description="The unique identifier for the chat thread.")
    response: str = Field(..., description="The AI's generated response in markdown format.")
    reasoning: Optional[str] = Field(None, description="Internal reasoning or routing logic used to generate the response.")
    requires_approval: bool = Field(False, description="Flag indicating if the action requires human approval before proceeding.")

class ChatThread(BaseModel):
    """Representation of a conversation thread."""
    thread_id: str = Field(..., description="Unique UUID for the conversation thread.")
    created_at: str = Field(..., description="ISO 8601 timestamp of when the thread was created.")
    updated_at: str = Field(..., description="ISO 8601 timestamp of the last activity in the thread.")
    last_message: Optional[str] = Field(None, description="The content of the most recent message in the thread.")
    message_count: int = Field(0, description="Total number of messages exchanged in this thread.")

class ChatHistoryItem(BaseModel):
    """A single message entry in the chat history."""
    role: str = Field(..., description="The role of the message sender ('user' or 'assistant').")
    message: str = Field(..., description="The text content of the message.")
    timestamp: str = Field(..., description="ISO 8601 timestamp of when the message was sent.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional structured metadata associated with the message (e.g., reasoning, tool usage).")
