"""
Message pruning and token management utilities.
Ensures conversation history stays within API token limits.
"""
from typing import List, Tuple
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
import re
from core.logger import logger


def estimate_tokens(text: str) -> int:
    """
    Rough estimate of token count. 
    Assumption: ~1 token per 4 characters (standard for LLMs).
    Actual token count may vary based on tokenizer.
    """
    return max(1, len(text) // 4)


def count_message_tokens(msg: BaseMessage) -> int:
    """Count approximate tokens in a single message."""
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return estimate_tokens(content)


def count_messages_tokens(messages: List[BaseMessage]) -> int:
    """Count approximate total tokens in a message list."""
    return sum(count_message_tokens(msg) for msg in messages)


def prune_messages_to_token_limit(
    messages: List[BaseMessage],
    token_limit: int = 4000,
    keep_first: bool = True,
    min_messages: int = 2
) -> List[BaseMessage]:
    """
    Intelligently prunes conversation history to stay within token limit.
    
    Strategy:
    1. Always keep the first message (user's initial context/goal)
    2. Keep as many recent messages as possible within token limit
    3. Maintain at least min_messages for context
    
    Args:
        messages: Full message history
        token_limit: Maximum tokens allowed (default 4000 to leave room for response)
        keep_first: Whether to keep the first message (recommended for context)
        min_messages: Minimum messages to keep
        
    Returns:
        Pruned message list within token budget
    """
    if not messages:
        return []
    
    total_tokens = count_messages_tokens(messages)
    
    if total_tokens <= token_limit:
        logger.debug(
            "Messages within token limit",
            current_tokens=total_tokens,
            limit=token_limit
        )
        return list(messages)
    
    logger.warning(
        "Messages exceed token limit, pruning",
        current_tokens=total_tokens,
        limit=token_limit,
        original_count=len(messages)
    )
    
    # Start from the end and work backwards, keeping recent messages
    pruned = []
    running_tokens = 0
    
    # Reserve space for first message if requested
    first_msg = messages[0] if keep_first else None
    first_tokens = count_message_tokens(first_msg) if first_msg else 0
    budget = token_limit - first_tokens
    
    # Add messages from most recent backwards
    for msg in reversed(messages[1:] if keep_first else messages):
        msg_tokens = count_message_tokens(msg)
        if running_tokens + msg_tokens <= budget and len(pruned) < 10:  # Max 10 recent messages
            pruned.append(msg)
            running_tokens += msg_tokens
        elif len(pruned) < min_messages:
            # Force add minimum messages even if over budget
            pruned.append(msg)
        else:
            break
    
    # Reverse back to chronological order
    pruned.reverse()
    
    # Add first message at the beginning if kept
    if first_msg:
        pruned = [first_msg] + pruned
    
    final_tokens = count_messages_tokens(pruned)
    logger.info(
        "Message pruning complete",
        original_count=len(messages),
        pruned_count=len(pruned),
        original_tokens=total_tokens,
        final_tokens=final_tokens
    )
    
    return pruned


def prune_by_conversation_exchanges(
    messages: List[BaseMessage],
    num_exchanges: int = 4,
    include_first: bool = True
) -> List[BaseMessage]:
    """
    Prune to keep only the last N conversation exchanges (human-AI pairs).
    
    This is a simpler approach that ensures semantic context is maintained
    while limiting to a manageable number of back-and-forths.
    
    Args:
        messages: Full message history
        num_exchanges: Number of human-AI pairs to keep (e.g., 4 = last 8 messages)
        include_first: Always include the first message for context
        
    Returns:
        Pruned message list with last N exchanges
    """
    if not messages:
        return []
    
    # Count AI messages to determine exchanges
    ai_count = sum(1 for msg in messages if msg.type == "ai")
    
    if ai_count <= num_exchanges:
        return list(messages)
    
    # Find the index where to start keeping messages
    ai_seen = 0
    target_ai_count = num_exchanges
    start_idx = 0
    
    for i, msg in enumerate(messages):
        if msg.type == "ai":
            ai_seen += 1
            if ai_seen > (ai_count - target_ai_count):
                start_idx = max(0, i - 1)  # Include preceding human message
                break
    
    if include_first and start_idx > 0:
        # Keep first message + recent exchanges
        pruned = [messages[0]] + messages[start_idx:]
    else:
        pruned = messages[start_idx:]
    
    logger.info(
        "Pruned to exchanges",
        original_count=len(messages),
        pruned_count=len(pruned),
        num_exchanges=num_exchanges
    )
    
    return pruned


def get_task_relevant_messages(
    messages: List[BaseMessage],
    current_user_message: str,
    max_messages: int = 10
) -> List[BaseMessage]:
    """
    Get messages most relevant to the current user's task.
    
    Looks for: the current user message + recent AI responses that 
    might contain the answer already.
    
    Args:
        messages: Full message history
        current_user_message: The user's latest query
        max_messages: Max messages to return
        
    Returns:
        Relevant message subset
    """
    if not messages:
        return []
    
    # Always include the current message
    relevant = []
    
    # Work backwards from the end to find recent exchanges
    for msg in reversed(messages):
        relevant.append(msg)
        if len(relevant) >= max_messages:
            break
    
    relevant.reverse()
    return relevant


def create_conversation_summary(messages: List[BaseMessage]) -> str:
    """
    Create a brief summary of conversation history.
    Useful for context injection when we need to prune but retain context.
    
    Args:
        messages: Full message history
        
    Returns:
        A summary string describing the conversation flow
    """
    if not messages:
        return "No conversation history."
    
    # Extract key points from the first and last few messages
    summary_points = []
    
    # First message (user's goal)
    if messages[0].type == "human":
        first_content = messages[0].content[:100]
        summary_points.append(f"Initial request: {first_content}...")
    
    # Count agent types used
    agents_used = set()
    for msg in messages:
        if msg.type == "ai":
            content = str(msg.content)
            if "database" in content.lower() or "sql" in content.lower():
                agents_used.add("sql")
            elif "document" in content.lower() or "search" in content.lower():
                agents_used.add("rag")
    
    if agents_used:
        summary_points.append(f"Agents consulted: {', '.join(agents_used)}")
    
    # Total messages
    summary_points.append(f"Total messages: {len(messages)}")
    
    return " | ".join(summary_points)


def clean_messages_from_xml_tags(messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Cleans conversation history by removing malformed XML-style tool calling tags.
    This prevents the model from imitating bad formats from previous failed attempts.
    
    Args:
        messages: List of messages to clean
        
    Returns:
        List of cleaned messages (new objects to avoid mutating original state)
    """
    cleaned = []
    # Pattern to match <function=...>{...}</function> and similar
    xml_pattern = re.compile(r'<function.*?>.*?</function>', re.DOTALL)
    tag_pattern = re.compile(r'</?function.*?>', re.DOTALL)
    
    for msg in messages:
        if isinstance(msg.content, str):
            # 1. Remove full XML blocks if they exist as text
            content = xml_pattern.sub('', msg.content)
            # 2. Remove stray tags
            content = tag_pattern.sub('', content)
            # 3. Clean up extra whitespace
            content = content.strip()
            
            # Create a shallow copy to avoid mutating original state if possible
            # or just update the content if it's a new list anyway
            if msg.type == "ai":
                # Create new AIMessage preserving critical fields
                new_msg = AIMessage(
                    content=content,
                    additional_kwargs=msg.additional_kwargs,
                    tool_calls=getattr(msg, "tool_calls", [])
                )
            elif msg.type == "human":
                new_msg = HumanMessage(content=content)
            else:
                new_msg = msg
            cleaned.append(new_msg)
        else:
            cleaned.append(msg)
            
    return cleaned
