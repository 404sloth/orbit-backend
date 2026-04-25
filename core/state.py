"""
Shared state definition for the Orbit multi-agent workflow.
All nodes read from and write to this single state object.
"""
import operator
from typing import Annotated, Sequence, TypedDict, Dict, Any, Optional, List
from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """The shared state for the multi-agent workflow.

    Attributes:
        messages: Append-only conversation history managed by LangGraph's reducer.
        next_node: The supervisor's routing instruction for the next agent.
        dashboard_data: Structured metrics and insights for the frontend dashboard.
        routing_reasoning: The supervisor's explanation for its routing decision.
        dynamic_suggestions: List[str]
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_node: str
    dashboard_data: Dict[str, Any]
    routing_reasoning: str
    dynamic_suggestions: List[str]