"""
Shared state definition for the Orbit multi-agent workflow.
All nodes read from and write to this single state object.
"""
import operator
from typing import Annotated, Sequence, TypedDict, Dict, Any, Optional, List
from langchain_core.messages import BaseMessage

def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    if not a:
        return b.copy() if b else {}
    if not b:
        return a.copy()
    return {**a, **b}

class GraphState(TypedDict):
    """The shared state for the multi-agent workflow.

    Attributes:
        messages: Append-only conversation history managed by LangGraph's reducer.
        next_node: The supervisor's routing instruction for the next agent.
        dashboard_data: Structured metrics and insights for the frontend dashboard.
        routing_reasoning: The supervisor's explanation for its routing decision.
        dynamic_suggestions: List[str]
        shared_context: Optional string for passing background data like schemas.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_node: str
    dashboard_data: Annotated[Dict[str, Any], merge_dicts]
    routing_reasoning: str
    dynamic_suggestions: Annotated[List[str], operator.add]
    shared_context: Optional[str]