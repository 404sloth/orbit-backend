from core.state import GraphState

def human_approval_node(state: GraphState) -> dict:
    """
    This node acts as a breakpoint. 
    LangGraph's checkpointer will pause execution right BEFORE this node runs.
    When execution resumes, it simply passes state forward.
    """
    return {"messages": []}