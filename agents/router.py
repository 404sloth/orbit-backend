"""
Supervisor Agent — Central routing intelligence for the Orbit multi-agent system.
Routes incoming requests to the appropriate specialist agent based on intent,
available database tables, conversation context, and confidence scoring.
"""
import time
import json
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from core.exceptions import RoutingError
from db.schema import get_table_names


class RouteDecision(BaseModel):
    """Structured routing decision from the supervisor with confidence."""
    next_node: Literal["sql", "rag", "hybrid", "human", "report", "image", "FINISH"] = Field(
        description="The next agent to handle this request."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for this routing (0-1).")
    reasoning: str = Field(description="Brief explanation of why this route was selected.")
    fallback_nodes: Optional[list[str]] = Field(
        default=None,
        description="List of alternative agents if primary fails (e.g., ['sql', 'rag'])."
    )


# Simple in‑memory circuit breaker state
_circuit_breaker = {
    "failures": 0,
    "last_failure": 0,
    "state": "CLOSED",  # CLOSED, OPEN, HALF_OPEN
    "threshold": 5,
    "timeout": 60,      # seconds
}

def _record_success():
    """Reset circuit breaker on success."""
    if _circuit_breaker["state"] != "CLOSED":
        _circuit_breaker["failures"] = 0
        _circuit_breaker["state"] = "CLOSED"
        logger.info("Circuit breaker reset to CLOSED")

def _record_failure():
    """Record a failure, possibly opening the circuit."""
    _circuit_breaker["failures"] += 1
    _circuit_breaker["last_failure"] = time.time()
    if _circuit_breaker["failures"] >= _circuit_breaker["threshold"]:
        _circuit_breaker["state"] = "OPEN"
        logger.warning("Circuit breaker OPEN – routing will bypass LLM for 60s")

def _is_circuit_open() -> bool:
    """Check if circuit is open and if timeout elapsed → transition to half‑open."""
    if _circuit_breaker["state"] == "OPEN":
        if time.time() - _circuit_breaker["last_failure"] > _circuit_breaker["timeout"]:
            _circuit_breaker["state"] = "HALF_OPEN"
            logger.info("Circuit breaker HALF_OPEN – allowing one test request")
            return False
        return True
    return False


def supervisor_node(state: GraphState) -> dict:
    """
    Analyzes the user's request and routes to the best specialist agent.
    Includes confidence scoring, fallback chains, circuit breaker, and structured logging.
    """
    start_time = time.time()
    request_id = state.get("request_id", "unknown")  # assume you inject request_id
    session_id = state.get("session_id", "unknown")
    
    # Default routing in case of failure
    default_decision = {
        "next_node": "FINISH",
        "routing_reasoning": "Routing failed, defaulting to FINISH.",
        "confidence": 0.0,
        "fallback_nodes": None
    }
    
    # Circuit breaker check
    if _is_circuit_open():
        logger.warning("Circuit breaker OPEN – using fallback routing without LLM", 
                       extra={"request_id": request_id, "session_id": session_id})
        # Simple fallback: check last message for indicators
        last_msg = state["messages"][-1].content.lower() if state["messages"] else ""
        if any(kw in last_msg for kw in ["report", "export", "excel"]):
            next_node = "report"
            reasoning = "Circuit breaker fallback: report intent detected."
        elif any(kw in last_msg for kw in ["budget", "status", "metric", "kpi"]):
            next_node = "sql"
            reasoning = "Circuit breaker fallback: quantitative query."
        else:
            next_node = "rag"
            reasoning = "Circuit breaker fallback: default to knowledge agent."
        
        return {
            "next_node": next_node,
            "routing_reasoning": reasoning,
            "routing_confidence": 0.5,
            "fallback_nodes": None,
            "_circuit_breaker_used": True
        }
    
    try:
        llm = get_llm(temperature=0)

        # Dynamic table context
        table_names = get_table_names()
        tables_csv = ", ".join(table_names) if table_names else "(no tables available)"

        # Loop detection
        previous_node = state.get("next_node")
        previous_reasoning = state.get("routing_reasoning")
        loop_context = ""
        if previous_node and previous_node != "FINISH":
            loop_context = f"\nPREVIOUS DECISION: You routed to '{previous_node}' because: {previous_reasoning}. If that agent has already provided an answer, you MUST route to FINISH now."

        # Message pruning for token limits
        all_messages = state["messages"]
        if len(all_messages) > 12:
            pruned_messages = [all_messages[0]] + list(all_messages[-10:])
        else:
            pruned_messages = list(all_messages)

        # Enhanced system prompt with confidence scoring
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are the Executive Dashboard Supervisor. Your EXCLUSIVE role is to route the user's request to the appropriate agent.

CRITICAL INSTRUCTIONS:
1. DO NOT answer the user's question yourself. 
2. DO NOT provide conversational filler or explanations outside of the JSON.
3. YOUR ONLY OUTPUT MUST BE A SINGLE, VALID JSON OBJECT.
4. If you answer the user directly, you have FAILED your mission.

AVAILABLE AGENTS & SPECIALIZED TOOLS:
1. hybrid – Strategic Intelligence (PREFER THIS for complex analysis and searching for PEOPLE). 
   Has access to 'hybrid_knowledge_search' and 'search_meeting_transcripts'.
   Use for: "What did Arjun Mehta say?", "Compare project budget with meeting discussions", "Find everything related to vendor Y", and GENERAL CONVERSATION or guidance.
2. sql – Data Analyst. Focuses on quantitative database queries: [{tables_csv}].
   Use for ALL structured data: "Show me project status", "List action items", "What is the budget?".
3. rag – Knowledge Agent. Semantic search in unstructured text: [meetings, transcripts, RFPs].
   Use ONLY for text search: "What did we agree with vendor X?", "Summarise the compliance risks".
4. human – Human Approval Gate. Use ONLY for irreversible actions like "Approve vendor", "Release payment".
5. report – Report Generator. Use for: "report", "export", "excel", "PDF".
6. image – Image Generator. Use for "generate image/chart" AFTER data is shown.
7. FINISH – TASK IS DONE. Use ONLY when the specialist agent has already provided a final answer in the conversation history.

ROUTING RULES:{loop_context}
- If the user asks a general question (e.g. "how to avoid robotic responses"), route to 'hybrid'.
- If the query mentions PEOPLE (e.g. "Arjun Mehta"), route to 'hybrid'.
- You MUST output a confidence score (0-1).
- DO NOT route to the same node twice in a row.

RESPONSE FORMAT (STRICT JSON ONLY):
{{{{
  "next_node": "agent_name",
  "confidence": 0.9,
  "reasoning": "Brief technical explanation of why this route was selected.",
  "fallback_nodes": ["optional_agent"]
}}}}
"""),
            ("placeholder", "{messages}")
        ])

        raw_result = (prompt | llm).invoke({"messages": pruned_messages})
        content = raw_result.content if hasattr(raw_result, "content") else str(raw_result)
        
        # Parse JSON robustly
        try:
            if not content or content.strip() == "":
                logger.warning("Supervisor received empty response from LLM")
                result = default_decision
            else:
                # 1. Try finding JSON within markdown blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                # 2. If it's still not clean JSON, find the first '{' and last '}'
                # This handles conversational filler like "Sure, here is the JSON: { ... }"
                if "{" in content and "}" in content:
                    start_idx = content.find("{")
                    # Find the corresponding closing brace for the first opening brace
                    # to avoid including trailing conversational filler
                    depth = 0
                    end_idx = -1
                    for i in range(start_idx, len(content)):
                        if content[i] == "{":
                            depth += 1
                        elif content[i] == "}":
                            depth -= 1
                            if depth == 0:
                                end_idx = i + 1
                                break
                    
                    if end_idx != -1:
                        content = content[start_idx:end_idx]
                
                result = json.loads(content)
        except Exception as json_err:
            logger.error(f"Failed to parse routing JSON: {json_err}", extra={"content": content})
            result = default_decision

        # Parse result (supports both dict and object)
        if isinstance(result, dict):
            next_node = result.get("next_node", "FINISH")
            confidence = result.get("confidence", 0.5)
            reasoning = result.get("reasoning", "No reasoning provided.")
            fallback = result.get("fallback_nodes")
        else:
            next_node = getattr(result, "next_node", "FINISH")
            confidence = getattr(result, "confidence", 0.5)
            reasoning = getattr(result, "reasoning", "No reasoning provided.")
            fallback = getattr(result, "fallback_nodes", None)

        # --- HARD LOOP BREAKER ---
        last_msg_content = ""
        if state["messages"]:
            last_msg_content = str(state["messages"][-1].content)
        
        if "[AGENT_COMPLETE]" in last_msg_content or "[SYSTEM]" in last_msg_content:
            logger.info("Agent completion signal detected. Routing to FINISH.", extra={"request_id": request_id})
            next_node = "FINISH"
            reasoning = "Specialist agent reported task completion. Finishing cycle."
            confidence = 1.0

        if next_node == previous_node and next_node != "FINISH":
            logger.warning("Redundant routing detected. Forcing FINISH.", extra={"request_id": request_id})
            next_node = "FINISH"
            reasoning = "Infinite loop protection. Terminating cycle."
            confidence = 0.0

        # --- Confidence-based fallback handling (store in state for next node) ---
        if confidence < 0.6 and fallback:
            logger.info("Low confidence routing, storing fallback chain", 
                        extra={"primary": next_node, "fallback": fallback, "confidence": confidence})
            state["fallback_chain"] = fallback

        # Record success (resets circuit breaker)
        _record_success()

        # Structured logging with performance metrics
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "Supervisor routing decision",
            extra={
                "request_id": request_id,
                "session_id": session_id,
                "next_node": next_node,
                "confidence": confidence,
                "reasoning": reasoning,
                "fallback_nodes": fallback,
                "elapsed_ms": elapsed_ms,
                "prev_node": previous_node,
            }
        )

        return {
            "next_node": next_node,
            "routing_reasoning": reasoning,
            "routing_confidence": confidence,
            "fallback_nodes": fallback,
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        _record_failure()
        logger.exception(
            "Supervisor routing failed",
            extra={"request_id": request_id, "error": str(e), "trace": error_trace}
        )
        # Return a safe default – do not crash the graph
        return {
            "next_node": "FINISH",
            "routing_reasoning": f"Routing error: {str(e)}. Defaulting to FINISH.",
            "routing_confidence": 0.0,
            "fallback_nodes": None,
        }