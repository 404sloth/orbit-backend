"""
Budget Tracking Agent - Comprehensive budget analysis and forecasting.
Uses create_react_agent for budget-focused intelligence.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from core.message_utils import prune_by_conversation_exchanges, clean_messages_from_xml_tags
from core.formatters import ResponseFormatter
from tools.budget import (
    get_project_budget_status,
    find_over_budget_projects,
    forecast_budget_completion,
    analyze_cost_by_milestone,
    compare_bid_vs_actual,
)


def budget_node(state: GraphState) -> dict:
    """
    Budget Tracking Agent node. Analyzes project budgets, forecasts, and identifies overruns.
    
    Provides:
    - Budget status and variance analysis
    - Over-budget project identification
    - Cost forecasting and projections
    - Budget vs actual comparisons
    """
    llm = get_llm(temperature=0)
    tools = [
        get_project_budget_status,
        find_over_budget_projects,
        forecast_budget_completion,
        analyze_cost_by_milestone,
        compare_bid_vs_actual,
    ]

    sys_msg = """You are the Budget Tracking Agent for an executive project dashboard.
Your job is to analyze project budgets, identify cost risks, and provide budget insights.

IMPORTANT: When you need to use a tool, you MUST output a valid JSON tool call. 
DO NOT use XML tags like <function> or </function>. 
DO NOT include any conversational filler, thoughts, or explanation before or after the tool call.

AVAILABLE TOOLS:
1. get_project_budget_status - Get detailed budget breakdown for a project
2. find_over_budget_projects - Identify projects exceeding budget
3. forecast_budget_completion - Project final cost at current burn rate
4. analyze_cost_by_milestone - Break down costs by milestone
5. compare_bid_vs_actual - Compare vendor bids with actual spending

WORKFLOW:
1. For budget questions, first get the project budget status or find over-budget projects
2. Use forecast_budget_completion to predict if project will exceed budget
3. Use analyze_cost_by_milestone to see spending patterns
4. Compare bid vs actual to identify cost variances
5. Provide clear interpretation with:
   - Current budget status (spent, remaining, percentage)
   - Trend analysis (burning faster/slower than planned)
   - Risk assessment (on track, warning, critical)
   - Recommendations (continue, monitor, reduce scope)

FORMATTING:
- Always format amounts with currency: $1,234,567
- Use percentages for progress: "45% spent"
- Highlight risks: "At 95% budget spend - CRITICAL"
- Show clear comparisons: "Spent: $800K of $1M budgeted"
- Provide actionable insights, not just data

RULES:
- Always provide currency formatting for budget amounts
- Use clear status indicators: ON TRACK | WARNING | CRITICAL
- When project is over budget, explain why and suggest corrective actions
- Keep responses concise and executive-friendly
- Focus on risks and trends, not just raw numbers

FINAL ANSWER:
State clearly what the budget situation is and what action, if any, is recommended.
"""

    try:
        agent_executor = create_react_agent(
            llm,
            tools,
            state_modifier=sys_msg
        )

        # Save subgraph diagram
        try:
            out_dir = pathlib.Path("graph_img")
            out_dir.mkdir(exist_ok=True)
            with open(out_dir / "budget_agent_latest.png", "wb") as f:
                f.write(agent_executor.get_graph().draw_mermaid_png())
        except Exception:
            pass

        # Prune messages
        all_messages = state["messages"]
        pruned_messages = prune_by_conversation_exchanges(
            all_messages,
            num_exchanges=4,
            include_first=True
        )
        
        # Clean any malformed XML tool tags from history
        pruned_messages = clean_messages_from_xml_tags(pruned_messages)

        original_len = len(all_messages)
        
        logger.info("Budget Agent invoked", original_msg_count=original_len, pruned_msg_count=len(pruned_messages))
        
        result = agent_executor.invoke(
            {"messages": pruned_messages},
            config={"recursion_limit": 15}
        )

        # Return only new messages
        all_messages_after = result["messages"]
        
        if len(all_messages_after) > len(pruned_messages):
            new_messages = all_messages_after[len(pruned_messages):]
        else:
            new_messages = all_messages_after if all_messages_after else []
        
        if not new_messages:
            from langchain_core.messages import SystemMessage
            new_messages = [SystemMessage(content="[AGENT_COMPLETE] Budget analysis complete.")]
        
        logger.info("Budget Agent finished", original_count=original_len, new_message_count=len(new_messages))
        
        return {"messages": new_messages}

    except Exception as e:
        logger.exception("Budget Agent execution failed")
        formatted_error = ResponseFormatter.format_error_response(
            error=str(e),
            context="Budget analysis"
        )
        return {"messages": [AIMessage(content=formatted_error)]}
