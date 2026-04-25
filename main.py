"""
Orbit API — FastAPI entry point for the Executive AI Dashboard.
Exposes POST /chat for React frontend integration.
"""
from fastapi import FastAPI, HTTPException, Depends, status, Request, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
import json
import asyncio
import io
from datetime import datetime, timedelta
from typing import List, Optional
import sqlite3
import uuid
from jose import jwt, JWTError

from langchain_core.messages import AIMessage, HumanMessage
from graph.build import build_workflow
from core.schemas import (
    ChatHistoryItem,
    ChatRequest,
    ChatResponse,
    ChatThread,
)
from core.logger import logger
from core.config import settings
from core.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    get_current_active_user,
    change_password,
    get_user,
    Token,
    UserBase,
    UserCreate,
    UserInDB,
    PasswordChange,
    RefreshTokenRequest,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SECRET_KEY,
    ALGORITHM,
)
from db.chat import (
    create_thread,
    delete_chat_thread,
    get_chat_history,
    get_chat_threads,
    save_chat_message,
    thread_exists,
)
from db.init_db import init_database
from core.parsers import get_parser_for_filename
from tools.rag import add_documents_to_knowledge_base
from core.session import init_reports_dir, cleanup_old_reports, REPORTS_TEMP_DIR
from db.dashboard import get_all_projects, get_project_timeline
import os

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for database and graph initialization."""
    # Initialize database if it doesn't exist
    db_path = settings.db_path
    if not os.path.exists(db_path):
        logger.info(f"Database not found at {db_path}. Initializing...")
        init_database()
        logger.info("Database initialized successfully.")

    # Initialize reports directory
    init_reports_dir()
    
    # Start background cleanup task
    async def cleanup_task():
        while True:
            try:
                cleanup_old_reports(max_age_seconds=3600)
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
            await asyncio.sleep(600) # Run every 10 minutes
            
    cleanup_loop = asyncio.create_task(cleanup_task())
    
    yield  # Server runs here
    
    # Shutdown logic
    cleanup_loop.cancel()
    logger.info("Orbit Backend shutting down.")

app = FastAPI(
    title="Orbit API",
    description="Executive AI Strategic Partner — Multi-Agent Dashboard Backend",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Build the workflow graph once on startup
try:
    graph = build_workflow()
    logger.info("Graph workflow initialized successfully.")
except Exception as e:
    logger.error("Failed to initialize graph workflow.", error=str(e))
    raise e


# Authentication endpoints
@app.post("/auth/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Login endpoint with enhanced security."""
    user = authenticate_user(form_data.username, form_data.password, request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(
        data={"sub": user.username, "role": user.role}
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=refresh_token
    )


@app.post("/auth/register", response_model=UserBase)
async def register(user_data: UserCreate):
    """Register a new user with validation."""
    try:
        user = create_user(user_data)
        return UserBase(
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@app.get("/auth/me", response_model=UserBase)
async def get_current_user_profile(current_user: UserInDB = Depends(get_current_active_user)):
    """Get current user profile."""
    return UserBase(
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active
    )


@app.post("/auth/change-password")
async def change_password_endpoint(
    password_data: PasswordChange,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Change user password."""
    if not change_password(current_user.username, password_data.current_password, password_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    return {"message": "Password changed successfully"}


@app.post("/auth/refresh", response_model=Token)
async def refresh_access_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    try:
        payload = jwt.decode(request.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        token_type: str = payload.get("type")

        if username is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Verify user still exists and is active
        user = get_user(username)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Create new access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": username, "role": role},
            expires_delta=access_token_expires
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint. Accepts a prompt and optional thread_id,
    routes through the multi-agent system, and returns the AI response.
    """
    logger.info(
        "Received chat request.",
        thread_id=request.thread_id,
        prompt_length=len(request.prompt),
    )

    thread_id = request.thread_id or str(uuid.uuid4())
    create_thread(thread_id)
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10,
    }

    current_state = graph.get_state(config)
    existing_messages = []
    if current_state is not None and current_state.values:
        existing_messages = current_state.values.get("messages", [])
        existing_messages = list(existing_messages)

    if not existing_messages:
        previous_history = get_chat_history(thread_id)
        for item in previous_history:
            if item["role"] == "assistant":
                existing_messages.append(AIMessage(content=item["message"]))
            else:
                existing_messages.append(HumanMessage(content=item["message"]))

    initial_state = {
        "messages": [*existing_messages, HumanMessage(content=request.prompt)],
        "dashboard_data": current_state.values.get("dashboard_data", {}) if current_state is not None and current_state.values else {},
    }

    try:
        # Check if graph is paused waiting for human approval
        if current_state is not None and getattr(current_state, "next", None) == ("human",):
            decision = request.prompt.strip().lower()
            save_chat_message(thread_id, "user", request.prompt)
            if decision in ["approve", "reject"]:
                logger.info("Received human decision.", decision=decision, thread_id=thread_id)
                graph.update_state(
                    config,
                    {"messages": [HumanMessage(content=f"Human action: {decision}")]},
                )
                final_ai_msg = None
                for event in graph.stream(None, config=config, stream_mode="values"):
                    latest_msg = event["messages"][-1]
                    if latest_msg.type == "ai" and not getattr(latest_msg, "tool_calls", None):
                        final_ai_msg = latest_msg.content

                if final_ai_msg:
                    save_chat_message(thread_id, "assistant", final_ai_msg)

                return ChatResponse(
                    thread_id=thread_id,
                    response=final_ai_msg or "Action finalized.",
                    requires_approval=False,
                )
            else:
                return ChatResponse(
                    thread_id=thread_id,
                    response="Execution paused. Human approval required. Reply with 'approve' or 'reject'.",
                    requires_approval=True,
                )

        # Standard execution path
        save_chat_message(thread_id, "user", request.prompt)

        final_ai_msg = None
        reasoning = None
        for event in graph.stream(initial_state, config=config, stream_mode="values"):
            # Ensure messages exist in the current state snapshot
            messages = event.get("messages")
            if not messages:
                continue
                
            latest_msg = messages[-1]
            if latest_msg.type == "ai" and not getattr(latest_msg, "tool_calls", None):
                content = str(latest_msg.content)
                if not content.startswith("[SYSTEM]") and not content.startswith("[AGENT_COMPLETE]"):
                    final_ai_msg = content
            
            if event.get("routing_reasoning"):
                reasoning = event["routing_reasoning"]

        # Check if execution paused on human node
        new_state = graph.get_state(config)
        if new_state is not None and getattr(new_state, "next", None) == ("human",):
            logger.warning("Execution paused for human approval.", thread_id=thread_id)
            return ChatResponse(
                thread_id=thread_id,
                response="[SYSTEM] Execution paused. Human approval required. Reply 'approve' or 'reject'.",
                requires_approval=True,
            )

        if final_ai_msg:
            save_chat_message(thread_id, "assistant", final_ai_msg)

        logger.info("Chat execution completed.", thread_id=thread_id)
        return ChatResponse(
            thread_id=thread_id,
            response=final_ai_msg or "No response generated.",
            reasoning=reasoning,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.exception("Chat execution error.", thread_id=thread_id)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@app.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming chat endpoint for real-time trace reasoning.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    create_thread(thread_id)
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    async def event_generator():
        save_chat_message(thread_id, "user", request.prompt)
        
        # Check if we are resuming from a human breakpoint
        current_state = graph.get_state(config)
        is_resuming = current_state is not None and getattr(current_state, "next", None) == ("human",)
        
        if is_resuming:
            decision = request.prompt.strip().lower()
            if decision in ["approve", "reject"]:
                graph.update_state(
                    config,
                    {"messages": [HumanMessage(content=f"Human action: {decision}")]},
                )
                initial_state = None # Resume from checkpoint
            else:
                # If not a valid decision, just treat as a normal message (which might be handled by supervisor if we wanted, but human node usually blocks)
                initial_state = {"messages": [HumanMessage(content=request.prompt)]}
        else:
            initial_state = {"messages": [HumanMessage(content=request.prompt)]}

        try:
            finished = False
            # We use stream_mode="updates" to get individual node outputs
            for chunk in graph.stream(initial_state, config=config, stream_mode="updates"):
                if finished: break
                for node_name, data in chunk.items():
                    # Send node start event
                    yield f"data: {json.dumps({'type': 'node_start', 'node': node_name})}\n\n"
                    
                    # Handle supervisor reasoning explicitly
                    if node_name == "supervisor":
                        next_node = data.get("next_node")
                        reasoning = data.get("routing_reasoning")
                        yield f"data: {json.dumps({'type': 'routing_decision', 'next_node': next_node, 'reasoning': reasoning})}\n\n"
                        if next_node == "FINISH":
                            finished = True
                    
                    # If it's a tool node, provide execution details
                    elif node_name == "call_tool":
                        # data might contain tool outputs
                        yield f"data: {json.dumps({'type': 'tool_use', 'node': node_name, 'data': str(data)})}\n\n"
                    
                    # If any agent returned a system complete message, signal it
                    elif "messages" in data:
                        for msg in data["messages"]:
                            content = str(msg.content)
                            if "[SYSTEM]" in content or "[AGENT_COMPLETE]" in content:
                                yield f"data: {json.dumps({'type': 'agent_status', 'status': 'completed', 'agent': node_name})}\n\n"
                            
                            # Detect report download links and signal them
                            if "reports/download/" in content:
                                import re
                                # Extract URL and filename
                                match = re.search(r'(https?://[^\s)]+/reports/download/([^\s)]+))', content)
                                if match:
                                    url = match.group(1).split(" ")[0].rstrip("->") # Clean up any trailing chars
                                    filename = match.group(2).split(" ")[0].rstrip("->")
                                    
                                    # Determine type based on extension
                                    if "xlsx" in filename:
                                        type_ = "excel"
                                    elif "zip" in filename:
                                        type_ = "image_bundle"
                                    else:
                                        type_ = "image"
                                        
                                    yield f"data: {json.dumps({'type': 'report_ready', 'url': url, 'filename': filename, 'report_type': type_})}\n\n"
                    
                    await asyncio.sleep(0.05) # Responsive but controlled flow

            # Check if graph is paused waiting for human approval
            final_state = graph.get_state(config)
            if final_state.next == ("human",):
                # Get the last AI message as the prompt for approval
                approval_prompt = "Approval required for high-impact action."
                for msg in reversed(final_state.values.get("messages", [])):
                    if msg.type == "ai" and msg.content:
                        approval_prompt = msg.content
                        break
                yield f"data: {json.dumps({'type': 'approval_required', 'prompt': approval_prompt})}\n\n"
            messages = final_state.values.get("messages", [])
            final_ai_msg = ""
            
            # Find the last message that isn't a system/control message
            for msg in reversed(messages):
                if msg.type == "ai" and not getattr(msg, "tool_calls", None):
                    content = str(msg.content)
                    if not content.startswith("[SYSTEM]") and not content.startswith("[AGENT_COMPLETE]"):
                        final_ai_msg = content
                        
                        # Detect Quick Actions (Proceed/Reject) based on content
                        if "proceed" in content.lower() or "generate image" in content.lower() or "approval" in content.lower():
                            yield f"data: {json.dumps({'type': 'quick_actions', 'actions': ['Proceed', 'Reject']})}\n\n"
                        break
            
            # --- Generate Smart Suggestions ---
            try:
                from agents.suggestion import suggestion_node
                # Run suggestion node outside the main graph for speed and clean state
                sugg_result = suggestion_node({"messages": messages})
                suggestions = sugg_result.get("dynamic_suggestions", [])
                if suggestions:
                    yield f"data: {json.dumps({'type': 'suggestions', 'queries': suggestions})}\n\n"
            except Exception as sugg_err:
                logger.error(f"Error in suggestion generation: {sugg_err}")
            
            reasoning = final_state.values.get("routing_reasoning")

            if final_ai_msg:
                save_chat_message(thread_id, "assistant", final_ai_msg)

            yield f"data: {json.dumps({'type': 'final_answer', 'response': final_ai_msg, 'reasoning': reasoning, 'thread_id': thread_id})}\n\n"
            
        except Exception as e:
            logger.exception("Streaming error")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat/threads", response_model=ChatThread)
async def create_chat_thread() -> ChatThread:
    thread_id = str(uuid.uuid4())
    create_thread(thread_id)
    return ChatThread(
        thread_id=thread_id,
        created_at=datetime.utcnow().isoformat() + "Z",
        updated_at=datetime.utcnow().isoformat() + "Z",
        last_message="",
        message_count=0,
    )


@app.get("/chat/threads", response_model=List[ChatThread])
async def list_chat_threads() -> List[ChatThread]:
    rows = get_chat_threads()
    return [
        ChatThread(
            thread_id=row["thread_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_message=row.get("last_message") or "",
            message_count=int(row.get("message_count") or 0),
        )
        for row in rows
    ]


@app.get("/chat/history/{thread_id}", response_model=List[ChatHistoryItem])
async def get_chat_history_endpoint(thread_id: str) -> List[ChatHistoryItem]:
    if not thread_exists(thread_id):
        raise HTTPException(status_code=404, detail="Chat thread not found")
    rows = get_chat_history(thread_id)
    return [
        ChatHistoryItem(role=row["role"], message=row["message"], timestamp=row["timestamp"])
        for row in rows
    ]


@app.post("/kb/documents")
async def ingest_knowledge(
    content: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """
    Ingest knowledge from either a text payload or an uploaded file.
    """
    try:
        final_content = ""
        final_source = source or "Manual Ingestion"

        if file:
            logger.info(f"Processing file upload: {file.filename}")
            parser = get_parser_for_filename(file.filename)
            if not parser:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")
            
            file_bytes = await file.read()
            final_content = parser(file_bytes)
            if not source:
                final_source = file.filename
        elif content:
            final_content = content
        else:
            raise HTTPException(status_code=400, detail="No content or file provided")

        if not final_content.strip():
            raise HTTPException(status_code=400, detail="Extracted content is empty")

        # Use the existing RAG tool logic
        result_json = add_documents_to_knowledge_base(final_content, final_source)
        result = json.loads(result_json)

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except Exception as e:
        logger.exception("Knowledge ingestion failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chat/threads/{thread_id}")
async def delete_chat_thread_endpoint(thread_id: str):
    if not thread_exists(thread_id):
        raise HTTPException(status_code=404, detail="Chat thread not found")
    delete_chat_thread(thread_id)
    return {"detail": "Chat thread deleted"}


@app.get("/dashboard/projects")
async def get_dashboard_projects():
    """Fetch projects for the Pulse page."""
    try:
        return get_all_projects()
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/projects/{project_id}/timeline")
async def get_dashboard_timeline(project_id: str):
    """Fetch unified timeline for a project."""
    try:
        return get_project_timeline(project_id)
    except Exception as e:
        logger.error(f"Failed to fetch timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dashboard/projects/{project_id}/simulate-full-lifecycle")
async def simulate_project_lifecycle(project_id: str):
    """Simulate a project progressing through its lifecycle."""
    # In a real app, this would trigger agent actions.
    # For now, we'll just return a success message.
    return {"message": f"Simulation started for project {project_id}"}


@app.get("/reports/download/{filename}")
async def download_report(filename: str):
    """
    Serves a generated Excel or image report file.
    Includes security checks to prevent path traversal.
    """
    # Prevent path traversal
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    file_path = os.path.join(REPORTS_TEMP_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or has expired")
        
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )


if __name__ == "__main__":
    import uvicorn
    # Use string reference to allow reload=True for persistent development mode
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
