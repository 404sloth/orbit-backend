"""
Centralized Pydantic schemas for all Orbit tools.
Provides strict type validation and rich descriptions for LLM tool binding.
"""
from pydantic import BaseModel, Field
from typing import Optional


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
    top_k: int = Field(
        default=3,
        description="Maximum number of relevant document chunks to return (1-10)."
    )

class AddDocumentsSchema(BaseModel):
    """Schema for the add_documents_to_knowledge_base tool."""
    content: str = Field(
        description="The text content to ingest into the vector database (meeting notes, requirements, etc.)."
    )
    source: str = Field(
        description="Descriptive source label for the document (e.g., 'Meeting Transcript - April 12')."
    )


# ========================== API Schemas ==========================

class ChatRequest(BaseModel):
    """Incoming chat request from the React frontend."""
    prompt: str
    thread_id: Optional[str] = None

class ChatResponse(BaseModel):
    """Outgoing chat response to the React frontend."""
    thread_id: str
    response: str
    reasoning: Optional[str] = None
    requires_approval: bool = False

class ChatThread(BaseModel):
    thread_id: str
    created_at: str
    updated_at: str
    last_message: Optional[str] = None
    message_count: int = 0

class ChatHistoryItem(BaseModel):
    role: str
    message: str
    timestamp: str
