"""
Graph Builder — Constructs and compiles the Orbit multi-agent StateGraph.
Manages the supervisor → agent → supervisor loop with SQLite persistence.
"""
import sqlite3
import pathlib
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import RemoveMessage
from core.state import GraphState
from core.logger import logger
from agents.router import supervisor_node
from agents.data import sql_node
from agents.knowledge import rag_node
from agents.hybrid import hybrid_node
from agents.report import report_node
from agents.image import image_node
from graph.edges import route_from_supervisor


def human_approval_node(state: GraphState) -> dict:
    """Breakpoint node. LangGraph interrupts BEFORE this executes."""
    return {"messages": []}

def trimmer_node(state: GraphState) -> dict:
    """Centralized message trimmer to manage token limits and prevent stale context bias."""
    messages = state.get("messages", [])
    # Keep only the last 15 messages for a rolling context window
    if len(messages) <= 15:
        return {}
    
    # Identify messages to remove (everything except the last 15)
    messages_to_remove = messages[:-15]
    
    # Only remove messages that have IDs (persisted messages)
    removals = [RemoveMessage(id=m.id) for m in messages_to_remove if getattr(m, "id", None)]
    
    if removals:
        logger.info("Trimmed stale messages from graph state", removed_count=len(removals))
        return {"messages": removals}
    return {}

def build_workflow():
    """
    Builds and compiles the full Orbit agent graph.

    Architecture:
        Entry → Trimmer → Supervisor → (sql | rag | human | report | image | FINISH)
        Workers always route back to Trimmer to ensure context window is managed.

    Returns:
        A compiled LangGraph CompiledGraph with SQLite checkpointing.
    """
    builder = StateGraph(GraphState)

    # Register nodes
    builder.add_node("trimmer", trimmer_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("sql", sql_node)
    builder.add_node("rag", rag_node)
    builder.add_node("hybrid", hybrid_node)
    builder.add_node("human", human_approval_node)
    builder.add_node("report", report_node)
    builder.add_node("image", image_node)

    # Entry point
    builder.set_entry_point("trimmer")
    builder.add_edge("trimmer", "supervisor")

    # Worker → Trimmer edges (workers always report back through trimmer)
    builder.add_edge("sql", "trimmer")
    builder.add_edge("rag", "trimmer")
    builder.add_edge("hybrid", "trimmer")
    builder.add_edge("human", "trimmer")
    builder.add_edge("report", "trimmer")
    builder.add_edge("image", "trimmer")

    # Supervisor conditional routing (using edges.py function)
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "sql": "sql",
            "rag": "rag",
            "hybrid": "hybrid",
            "human": "human",
            "report": "report",
            "image": "image",
            "FINISH": END,
        }
    )


    # SQLite persistence for session continuity
    conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
    memory = SqliteSaver(conn)
    memory.setup()

    logger.info("Building workflow graph with SqliteSaver persistence.")
    graph = builder.compile(
        checkpointer=memory,
        interrupt_before=["human"]
    )

    # Auto-generate agent diagrams
    _generate_agent_diagrams(graph)

    return graph


def _generate_agent_diagrams(graph) -> None:
    """Saves the compiled supervisor graph diagram as a PNG."""
    out_dir = pathlib.Path("graph_img")
    out_dir.mkdir(exist_ok=True)

    try:
        diagram_data = graph.get_graph().draw_mermaid_png()
        out_path = out_dir / "supervisor_latest.png"
        with open(out_path, "wb") as f:
            f.write(diagram_data)
        logger.info("Saved agent diagram", path=str(out_path))
    except Exception as e:
        logger.error("Failed to generate agent diagrams", error=str(e))