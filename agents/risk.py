"""
Risk Management Agent - Identifies, assesses, and tracks project risks.
Uses create_react_agent for intelligent risk analysis.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from core.message_utils import prune_by_conversation_exchanges, clean_messages_from_xml_tags
from core.formatters import ResponseFormatter
from tools.risk import (
    assess_project_risks,
    identify_at_risk_projects,
    analyze_milestone_delays,
    identify_risk_patterns,
)


def risk_node(state: GraphState) -> dict:
    """
    Risk Management Agent node. Analyzes project risks and provides mitigation guidance.
    
    Provides:
    - Risk assessment and scoring
    - At-risk project identification
    - Delay pattern analysis
    - Risk trend analysis across portfolio
    """
    llm = get_llm(temperature=0)
    tools = [
        assess_project_risks,
        identify_at_risk_projects,
        analyze_milestone_delays,
        identify_risk_patterns,
    ]

    sys_msg = """You are the Risk Management Agent for an executive project dashboard.
Your job is to identify, assess, and help mitigate project risks.

IMPORTANT: When you need to use a tool, you MUST output a valid JSON tool call. 
DO NOT use XML tags like <function> or </function>. 
DO NOT include any conversational filler, thoughts, or explanation before or after the tool call.

AVAILABLE TOOLS:
1. assess_project_risks - Get comprehensive risk score and breakdown for a project
2. identify_at_risk_projects - Find all projects currently at risk across portfolio
3. analyze_milestone_delays - Analyze delays and their timeline impact
4. identify_risk_patterns - Find common risks across projects

WORKFLOW:
1. For risk assessment, use assess_project_risks for specific projects or identify_at_risk_projects for overview
2. Analyze delays using analyze_milestone_delays to understand timeline impact
3. Use identify_risk_patterns to spot portfolio-wide issues
4. Provide risk interpretation with:
   - Overall risk score (0-100)
   - Risk level indicator (CRITICAL/HIGH/MEDIUM/LOW)
   - Breakdown by category (timeline, budget, resource, technical)
   - Key issues and root causes
   - Recommended mitigation actions

RISK LEVEL INDICATORS:
- CRITICAL (75-100): Immediate action required
- HIGH (50-74): Close monitoring and planned interventions
- MEDIUM (25-49): Regular monitoring
- LOW (0-24): Standard tracking

FORMATTING:
- Use risk score: "Risk Score: 72/100 HIGH"
- List risks clearly with impact assessment
- Provide specific, actionable recommendations
- Show metrics: "3/15 milestones delayed (20%)"
- Highlight trends: "Delays increasing over time"

RULES:
- Always provide risk score and level indicator
- Prioritize by impact: critical > timeline > budget > resource
- Be specific about what's at risk (budget amount, timeline days, scope items)
- Suggest concrete actions, not generic advice
- Focus on preventable and controllable risks

FINAL ANSWER:
State clearly what the risks are, their severity, and what actions should be taken.
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
            with open(out_dir / "risk_agent_latest.png", "wb") as f:
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
        
        logger.info("Risk Agent invoked", original_msg_count=original_len, pruned_msg_count=len(pruned_messages))
        
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
            new_messages = [SystemMessage(content="[AGENT_COMPLETE] Risk analysis complete.")]
        
        logger.info("Risk Agent finished", original_count=original_len, new_message_count=len(new_messages))
        
        return {"messages": new_messages}

    except Exception as e:
        logger.exception("Risk Agent execution failed")
        formatted_error = ResponseFormatter.format_error_response(
            error=str(e),
            context="Risk analysis"
        )
        return {"messages": [AIMessage(content=formatted_error)]}
