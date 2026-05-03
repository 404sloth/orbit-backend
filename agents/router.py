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
    logger.info("Supervisor node started", extra={"request_id": state.get("request_id")})
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

        # Pass standard messages to the LLM, filtering out internal LangGraph artifacts
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
        raw_messages = state.get("messages", [])

        # Loop detection and termination
        previous_node = state.get("next_node")
        previous_reasoning = state.get("routing_reasoning")
        
        # If a specialist has already answered, we should likely FINISH
        last_msg = raw_messages[-1] if raw_messages else None
        has_final_answer = isinstance(last_msg, AIMessage) and not getattr(last_msg, "tool_calls", None)
        
        loop_context = ""
        if previous_node and previous_node != "FINISH":
            if has_final_answer:
                logger.info("Specialist already provided final answer, forcing FINISH", node=previous_node)
                return {
                    "next_node": "FINISH",
                    "routing_reasoning": f"Agent '{previous_node}' has already provided a final answer. Ending conversation.",
                    "routing_confidence": 1.0,
                    "fallback_nodes": None,
                }
            loop_context = f"\nPREVIOUS DECISION: You routed to '{previous_node}' because: {previous_reasoning}. If that agent has already provided an answer, you MUST route to FINISH now."

        pruned_messages = [
            m for m in raw_messages 
            if isinstance(m, (HumanMessage, AIMessage, SystemMessage, ToolMessage))
        ]

        # Enhanced system prompt with confidence scoring
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are the Executive Dashboard Supervisor. Your EXCLUSIVE role is to route the user's request to the appropriate agent.

CRITICAL INSTRUCTIONS:
1. DO NOT answer the user's question yourself. 
2. DO NOT provide conversational filler or explanations outside of the JSON.
3. YOUR ONLY OUTPUT MUST BE A SINGLE, VALID JSON OBJECT.
4. If you answer the user directly, you have FAILED your mission.

AVAILABLE AGENTS & MISSION PARAMETERS:
1. sql (Data Analyst): USE THIS for all structured data, lists, and quantitative metrics from the database (projects, credits, milestones).
2. rag (Knowledge Agent): USE THIS for searching through unstructured documents, proposals, and project notes.
3. hybrid (Strategic Intelligence): USE THIS for cross-functional analysis, people-centric queries (transcripts), and complex reasoning that combines SQL and RAG.
4. report (Executive Report Agent): USE THIS EXCLUSIVELY for generating formal PDF, DOCX, or Excel documents/reports.
5. image (Creative Agent): USE THIS for generating UI mockups, project logos, or visual assets.
6. human (Advisory): USE THIS only if the request is highly ambiguous or requires human-in-the-loop approval.
7. FINISH (Task Complete): USE THIS immediately once a specialist agent has provided a final answer.

ROUTING RULES:
- If the user asks to "Generate a report", "Export to Excel", or "Make a PDF", ROUTE TO 'report'.
- If the user asks about project metrics or lists, ROUTE TO 'sql'.
- If the last message is a final response from an agent, ROUTE TO 'FINISH'.
- DO NOT answer the user yourself.

RESPONSE FORMAT (STRICT JSON ONLY):
{{{{
  "next_node": "sql" | "rag" | "hybrid" | "report" | "image" | "human" | "FINISH",
  "confidence": 0.0 to 1.0,
  "reasoning": "Specify exactly which data or tool is targeted.",
  "fallback_nodes": ["optional"]
}}}}
{loop_context}
"""),
            ("placeholder", "{messages}")
        ])

        raw_result = (prompt | llm).invoke({"messages": pruned_messages})
        if not raw_result or not raw_result.content.strip():
            logger.warning("Supervisor received empty response from LLM")
            return {
                "next_node": "hybrid",
                "routing_reasoning": "Supervisor failed to decide (empty response), falling back to hybrid specialist.",
                "routing_confidence": 0.1,
                "fallback_nodes": None,
            }

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