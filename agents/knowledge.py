"""
Project Knowledge Agent — Handles unstructured document search and ingestion.
Uses create_react_agent for multi-step RAG reasoning.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import RunnableConfig
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from tools.rag import search_project_documents, add_documents_to_knowledge_base


def rag_node(state: GraphState, config: RunnableConfig) -> dict:
    """
    Knowledge Agent sub-agent node. Searches and ingests
    unstructured project documents via ChromaDB.
    """
    llm = get_llm(temperature=0)
    
    # Retrieve user context from config
    user_id = config.get("configurable", {}).get("user_id")
    username = config.get("configurable", {}).get("username", "Executive")
    role = config.get("configurable", {}).get("role", "USER")

    # Define tools with user context partially applied or handled within tool
    tools = [search_project_documents, add_documents_to_knowledge_base]

    sys_msg = f"""You are the Project Knowledge Agent for an executive dashboard.
Your job is to search through and manage the unstructured knowledge base containing
meeting transcripts, vendor proposals, requirements documents, and project notes.

SECURITY CONTEXT:
- CURRENT USER: {username} (ID: {user_id}, Role: {role})
- PRIVACY RULE: You must ONLY access documents that are either 'global' or marked as 'personal' for your User ID ({user_id}).
- DATA ISOLATION: Never reveal or search for documents belonging to other user IDs.

STRICT TOOL CALLING RULES:
- Use ONLY standard ASCII straight double-quotes (") for JSON keys and strings.
- NEVER use curly quotes (“ or ”).
- NEVER wrap tool calls in XML-like tags like <function=...>. 
- Call tools ONE AT A TIME. Do not attempt parallel tool calling.
- Ensure all JSON is perfectly formatted.

AVAILABLE TOOLS:
1. search_project_documents — Semantic search across all stored documents.
2. add_documents_to_knowledge_base — Ingest new text into the knowledge base.

WORKFLOW:
1. ALWAYS use search_project_documents first to find relevant information.
2. If the user provides new text/transcript to save, use add_documents_to_knowledge_base.
3. When presenting search results, CITE the source explicitely using the tag provided by the search tool.
4. If no relevant documents are found, clearly state that.

RULES:
- Never hallucinate information that isn't in the search results.
- Always cite your sources using the EXACT source string provided in the search results.
- Synthesize multiple document results into a coherent executive summary.
- Professional, executive-grade responses only.
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

        # Filter for standard messages to ensure LLM compatibility (especially for Groq)
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
        raw_messages = state.get("messages", [])
        pruned_messages = [
            m for m in raw_messages 
            if isinstance(m, (HumanMessage, AIMessage, SystemMessage, ToolMessage))
        ]

        # Capture original length BEFORE invocation to avoid mutation bugs
        pruned_len = len(pruned_messages)
        result = agent_executor.invoke({"messages": pruned_messages}, config=config)

        # Return only new AI messages to keep the global state clean
        all_messages_after = result["messages"]
        new_messages = []
        if len(all_messages_after) > pruned_len:
            # Only keep the FINAL response to avoid dangly tool_call metadata
            from langchain_core.messages import AIMessage
            final_msg = all_messages_after[-1]
            if isinstance(final_msg, AIMessage):
                clean_m = AIMessage(content=final_msg.content)
                new_messages.append(clean_m)
        
        if not new_messages:
            # Fallback if no AI message was produced
            from langchain_core.messages import SystemMessage
            new_messages = [SystemMessage(content="[SYSTEM] Knowledge Agent reviewed the data but produced no final summary.")]

        return {"messages": new_messages}

    except Exception as e:
        logger.exception("RAG Agent execution failed")
        from langchain_core.messages import AIMessage
        err_msg = str(e) if str(e).strip() else repr(e)
        return {
            "messages": [AIMessage(content=f"Knowledge Agent Error: {err_msg}. Please try rephrasing your question.")]
        }