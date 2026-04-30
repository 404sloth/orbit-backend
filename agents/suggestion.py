"""
Suggestion Agent - Generates intelligent follow-up queries based on conversation context.
"""
import json
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger

def suggestion_node(state: GraphState) -> dict:
    """
    Analyzes the conversation and generates 3 relevant follow-up questions.
    """
    logger.info("Generating smart suggestions")
    
    llm = get_llm(temperature=0.7) # Higher temperature for variety
    
    # Prune messages for context
    all_messages = state["messages"]
    context_messages = all_messages[-5:] if len(all_messages) > 5 else all_messages
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an executive assistant. Based on the conversation history, generate exactly 3 short, relevant, and proactive follow-up questions or actions that the user might want to take next.
        
Guidelines:
- Keep them under 10 words each.
- Be specific to the data or topics discussed.
- If a report was just generated, suggest visualizing it or comparing it to other data.
- If a problem was identified, suggest looking into the root cause.
- Format your response as a JSON array of strings.

Example Output:
["Show budget breakdown by vendor", "Compare with last month's status", "Identify top 3 at-risk milestones"]
"""),
        ("placeholder", "{messages}")
    ])
    
    try:
        chain = prompt | llm
        response = chain.invoke({"messages": context_messages})
        content = response.content.strip()
        
        # 1. Try finding JSON within markdown blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        # 2. Robust array extraction
        if "[" in content and "]" in content:
            start_idx = content.find("[")
            end_idx = content.rfind("]") + 1
            content = content[start_idx:end_idx]

            
        suggestions = json.loads(content)
        if not isinstance(suggestions, list) or not suggestions:
            raise ValueError("Invalid or empty suggestions list")
        
        # Ensure exactly 3 and clean them
        suggestions = [str(s)[:100] for s in suggestions[:3]]
        
        logger.info("Suggestions generated", count=len(suggestions))
        return {"dynamic_suggestions": suggestions}
        
    except Exception as e:
        logger.error("Failed to generate suggestions, using defaults", error=str(e))
        return {"dynamic_suggestions": [
            "Show project budget status",
            "Identify delayed tasks",
            "Generate weekly summary"
        ]}
