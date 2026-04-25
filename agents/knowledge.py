"""
Project Knowledge Agent — Handles unstructured document search and ingestion.
Uses create_react_agent for multi-step RAG reasoning.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from tools.rag import search_project_documents, add_documents_to_knowledge_base


def rag_node(state: GraphState) -> dict:
    """
    Knowledge Agent sub-agent node. Searches and ingests
    unstructured project documents via ChromaDB.

    Steps:
    1. Creates a ReAct agent with RAG tools.
    2. Executes the agent and returns only new messages.
    """
    llm = get_llm(temperature=0)
    tools = [search_project_documents, add_documents_to_knowledge_base]

    sys_msg = """You are the Project Knowledge Agent for an executive dashboard.
Your job is to search through and manage the unstructured knowledge base containing
meeting transcripts, vendor proposals, requirements documents, and project notes.

AVAILABLE TOOLS:
1. search_project_documents — Semantic search across all stored documents.
2. add_documents_to_knowledge_base — Ingest new text into the knowledge base.

WORKFLOW:
1. ALWAYS use search_project_documents first to find relevant information.
2. If the user provides new text/transcript to save, use add_documents_to_knowledge_base.
3. When presenting search results, CITE the source metadata explicitly:
   e.g., "According to [Meeting Transcript - April 12]..."
4. If no relevant documents are found, clearly state that and suggest
   the user may need to ingest the relevant documents first.

RULES:
- Never hallucinate information that isn't in the search results.
- Always cite your sources with the document source label.
- Synthesize multiple document results into a coherent executive summary.
"""

    try:
        agent_executor = create_react_agent(llm, tools, state_modifier=sys_msg)

        # Save subgraph diagram
        try:
            out_dir = pathlib.Path("graph_img")
            out_dir.mkdir(exist_ok=True)
            with open(out_dir / "rag_agent_latest.png", "wb") as f:
                f.write(agent_executor.get_graph().draw_mermaid_png())
        except Exception:
            pass

        # ROOT FIX: Prune messages to stay within Groq TPM limits
        all_messages = state["messages"]
        if len(all_messages) > 12:
            pruned_messages = [all_messages[0]] + list(all_messages[-10:])
        else:
            pruned_messages = list(all_messages)

        # Capture original length BEFORE invocation to avoid mutation bugs
        # We use the length of pruned_messages because that's what the agent executor starts with
        pruned_len = len(pruned_messages)
        result = agent_executor.invoke({"messages": pruned_messages})

        # Return only new messages
        all_messages_after = result["messages"]
        if len(all_messages_after) > pruned_len:
            new_messages = all_messages_after[pruned_len:]
        else:
            # If for some reason it's shorter or same length, assume no new messages
            new_messages = []
        
        logger.info(
            "RAG Agent finished",
            in_count=len(state["messages"]),
            out_count=len(all_messages_after),
            new_count=len(new_messages)
        )
        
        if not new_messages:
            from langchain_core.messages import SystemMessage
            new_messages = [SystemMessage(content="[SYSTEM] Knowledge Agent reviewed the history and found no new actions needed.")]

        return {"messages": new_messages}

    except Exception as e:
        logger.exception("RAG Agent execution failed")
        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content=f"Knowledge Agent Error: {str(e)}. Please try rephrasing your question.")]
        }