"""
Graph edge routing functions.
Used by the StateGraph's conditional_edges to map supervisor decisions to nodes.
"""
from langgraph.graph import END
from core.state import GraphState


def route_from_supervisor(state: GraphState) -> str:
    """
    Reads the supervisor's routing decision from state and returns
    the corresponding node name.

    Args:
        state: The current GraphState containing 'next_node'.

    Returns:
        A string matching one of the registered node names or END.
    """
    decision = state.get("next_node", "FINISH")

    valid_routes = {"sql", "rag", "hybrid", "human", "report", "image"}
    if decision in valid_routes:
        return decision

    return "FINISH"