"""
Custom exception hierarchy for Orbit agent system.
Provides granular error classification instead of catching generic Exception.
"""


class OrbitError(Exception):
    """Base exception for all Orbit-specific errors."""
    pass


class DatabaseQueryError(OrbitError):
    """Raised when a SQL query fails to execute against the database."""
    pass


class RetrievalError(OrbitError):
    """Raised when the RAG vector-search pipeline fails."""
    pass


class RoutingError(OrbitError):
    """Raised when the supervisor cannot determine a valid route."""
    pass


class ToolExecutionError(OrbitError):
    """Raised when a tool invocation fails internally."""
    pass


class SchemaIntrospectionError(OrbitError):
    """Raised when reading database schema or table names fails."""
    pass
