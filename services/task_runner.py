"""
Asynchronous Task Runner for Background Agents
Provides a lightweight way to execute LangGraph agents autonomously
without blocking the main API thread.
"""
import asyncio
import uuid
from typing import Optional
from langchain_core.messages import HumanMessage
from core.logger import logger
from graph.build import build_workflow
from db.chat import create_thread, save_chat_message

class AgentTaskRunner:
    """Manages the execution of background agent tasks."""
    
    def __init__(self):
        # We use a lazily initialized graph to avoid circular imports during startup
        self._graph = None

    @property
    def graph(self):
        if not self._graph:
            self._graph = build_workflow()
        return self._graph

    async def run_task_detached(self, prompt: str, user_id: int, username: str, role: str = "USER") -> str:
        """
        Executes a prompt through the multi-agent system in the background.
        Returns the thread_id for tracking.
        """
        thread_id = str(uuid.uuid4())
        create_thread(thread_id, user_id=user_id)
        
        # Save initial prompt
        save_chat_message(thread_id, "user", prompt, user_id=user_id)
        
        # Fire and forget the background execution
        asyncio.create_task(self._execute_graph(thread_id, prompt, user_id, username, role))
        
        logger.info(f"Started background agent task", thread_id=thread_id)
        return thread_id

    async def _execute_graph(self, thread_id: str, prompt: str, user_id: int, username: str, role: str):
        """Internal coroutine to run the graph and persist the result."""
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
                "username": username,
                "role": role
            },
            "recursion_limit": 15,
        }
        
        initial_state = {
            "messages": [HumanMessage(content=prompt)],
            "dashboard_data": {}
        }
        
        try:
            final_ai_msg = None
            reasoning = None
            
            # Run graph synchronously but offloaded if needed, though LangGraph stream blocks.
            # Using asyncio.to_thread for blocking graph execution
            def run_sync():
                f_msg = None
                r_reasoning = None
                for event in self.graph.stream(initial_state, config=config, stream_mode="values"):
                    messages = event.get("messages", [])
                    if messages:
                        latest = messages[-1]
                        if latest.type == "ai" and not getattr(latest, "tool_calls", None):
                            content = str(latest.content)
                            if not content.startswith("[SYSTEM]") and not content.startswith("[AGENT_COMPLETE]"):
                                f_msg = content
                    if event.get("routing_reasoning"):
                        r_reasoning = event["routing_reasoning"]
                return f_msg, r_reasoning

            final_ai_msg, reasoning = await asyncio.to_thread(run_sync)
            
            if final_ai_msg:
                save_chat_message(thread_id, "assistant", final_ai_msg, user_id=user_id, metadata={"reasoning": reasoning})
                logger.info("Background agent task completed successfully.", thread_id=thread_id)
            else:
                logger.warning("Background agent task completed but produced no output.", thread_id=thread_id)
                
        except Exception as e:
            logger.error(f"Background agent task failed: {e}", thread_id=thread_id)
            save_chat_message(thread_id, "assistant", f"[SYSTEM ERROR] Task failed: {str(e)}", user_id=user_id)

# Singleton instance
task_runner = AgentTaskRunner()
