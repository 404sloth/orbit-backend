"""
Report Agent - Handles Excel and PDF generation.
Refactored as a ReAct agent for multi-tool orchestration.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import RunnableConfig
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from tools.document import generate_executive_report
from services.schema_cache import get_cached_schema

def report_node(state: GraphState, config: RunnableConfig) -> dict:
    """
    Report Agent node. Uses ReAct agent to decide between 
    SQL queries and PDF document generation.
    """
    llm = get_llm(temperature=0)
    tools = [
        generate_executive_report,
    ]

    # Retrieve dynamic schema context from cache (more token-efficient)
    cached_schema = get_cached_schema()
    detailed_schema = cached_schema.get("detailed_schema", "No details available.")



    username = config.get("configurable", {}).get("username", "Executive")
    role = config.get("configurable", {}).get("role", "USER")

    sys_msg = f"""You are the Executive Report Agent. 
Your job is to generate professional documents (PDF, DOCX) or data spreadsheets (Excel).

CURRENT USER: {username} (Role: {role})

CAPABILITIES:
1. DOCUMENTS: Use generate_executive_report to create premium summaries, RFPs, SOWs, or spreadsheets using the data already provided in the conversation. DO NOT attempt to fetch new data.

DATABASE SCHEMA:
{detailed_schema}

STRICT TOOL CALLING RULES:
- Use ONLY standard ASCII straight double-quotes (") for JSON keys and strings.
- NEVER use curly quotes (“ or ”).
- NEVER wrap tool calls in XML-like tags like <function=...>. 
- Ensure all JSON is perfectly formatted.
- Call tools ONE AT A TIME.

WORKFLOW:
1. DATA FOCUS: If the user wants a data export or spreadsheet, use format='EXCEL'.
2. DOCUMENT FOCUS: Use format='PDF' (default) or 'DOCX' as needed.
3. For PDF/DOCX, provide RICH and DETAILED content_markdown.

RULES:
- Include executive summaries, key findings, and action items.
- Always include the download link provided by the tool in your final response.
- Keep your confirmation concise and professional.
- Use standard Markdown tables for data representation.
"""

    try:
        agent_executor = create_react_agent(llm, tools, state_modifier=sys_msg)

        # Prune messages
        all_messages = state["messages"]
        if len(all_messages) > 12:
            pruned_messages = [all_messages[0]] + list(all_messages[-10:])
        else:
            pruned_messages = list(all_messages)

        pruned_len = len(pruned_messages)
        
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = agent_executor.invoke({"messages": pruned_messages}, config=config)
                break
            except Exception as e:
                err_str = str(e)
                if "tool_use_failed" in err_str or "invalid_request_error" in err_str or "Failed to call" in err_str:
                    if attempt < max_retries - 1:
                        logger.warning(f"Report Agent tool call failed (attempt {attempt + 1}), retrying...", error=err_str)
                        continue
                raise

        # Return only the final AI message to keep the global state clean
        all_messages_after = result["messages"]
        new_messages = []
        if len(all_messages_after) > pruned_len:
            from langchain_core.messages import AIMessage
            final_msg = all_messages_after[-1]
            if isinstance(final_msg, AIMessage):
                # Strip metadata to prevent tool_call residue in the supervisor loop
                clean_m = AIMessage(content=final_msg.content)
                new_messages.append(clean_m)
        
        logger.info(
            "Report Agent finished",
            in_count=len(state["messages"]),
            new_count=len(new_messages)
        )
        
        return {"messages": new_messages}

    except Exception as e:
        logger.exception("Report Agent failed")
        from langchain_core.messages import AIMessage
        err_msg = str(e) if str(e) else repr(e)
        return {
            "messages": [AIMessage(content=f"Report Agent Error: {err_msg}")]
        }
