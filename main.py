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
    CreditDeductionRequest,
    VendorBillRequest,
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
from db.dashboard import get_all_projects, get_project_timeline, get_pending_notifications, update_notification_status
from db.audit import get_access_gaps
from db.suggestions import get_dynamic_suggestions
from services.credit_service import CreditService
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
@app.post("/auth/login", response_model=Token, tags=["Authentication"], summary="User Login", description="Authenticates a user with username and password, returning a JWT access token and refresh token.")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Login endpoint with enhanced security.
    Validates credentials and generates secure JWT tokens.
    """
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


@app.post("/auth/register", response_model=UserBase, tags=["Authentication"], summary="Register New User", description="Creates a new user account with the provided details.")
async def register(user_data: UserCreate):
    """
    Register a new user with validation.
    Ensures username and email uniqueness and enforces password strength policies.
    """
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


@app.get("/auth/me", response_model=UserBase, tags=["Authentication"], summary="Get Current User", description="Retrieves the profile information of the currently authenticated user.")
async def get_current_user_profile(current_user: UserInDB = Depends(get_current_active_user)):
    """Get current user profile from the active session."""
    return UserBase(
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active
    )


@app.post("/auth/change-password", tags=["Authentication"], summary="Change Password", description="Updates the password for the currently authenticated user.")
async def change_password_endpoint(
    password_data: PasswordChange,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Change user password.
    Requires the current password for verification before setting the new password.
    """
    if not change_password(current_user.username, password_data.current_password, password_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    return {"message": "Password changed successfully"}


@app.post("/auth/refresh", response_model=Token, tags=["Authentication"], summary="Refresh Access Token", description="Generates a new JWT access token using a valid refresh token.")
async def refresh_access_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token.
    Extends the user's session without requiring re-authentication.
    """
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


@app.post("/chat", response_model=ChatResponse, tags=["Chat"], summary="Sync Chat", description="Sends a prompt to the multi-agent system and waits for a complete response.")
async def chat_endpoint(request: ChatRequest, current_user: UserInDB = Depends(get_current_active_user)):
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
        "configurable": {
            "thread_id": thread_id,
            "user_id": current_user.user_id,
            "username": current_user.username
        },
        "recursion_limit": 10,
    }

    current_state = graph.get_state(config)
    existing_messages = []
    if current_state is not None and current_state.values:
        existing_messages = current_state.values.get("messages", [])
        existing_messages = list(existing_messages)

    if not existing_messages:
        previous_history = get_chat_history(thread_id, user_id=current_user.user_id)
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

                # Persist assistant's final response with metadata
                save_chat_message(
                    thread_id=thread_id,
                    role="assistant",
                    content=final_ai_msg,
                    metadata={"reasoning": None}
                )

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


@app.post("/chat/stream", tags=["Chat"], summary="Streaming Chat", description="Initiates a streaming chat session for real-time AI reasoning and responses.")
async def chat_stream_endpoint(request: ChatRequest, current_user: UserInDB = Depends(get_current_active_user)):
    """
    Streaming chat endpoint for real-time trace reasoning.
    Provides Server-Sent Events (SSE) for incremental updates.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    create_thread(thread_id)
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": current_user.user_id,
            "username": current_user.username,
            "role": current_user.role
        },
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
            reported_urls = set()
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
                                    elif "pdf" in filename:
                                        type_ = "pdf"
                                    else:
                                        type_ = "image"
                                        
                                    if url not in reported_urls:
                                        yield f"data: {json.dumps({'type': 'report_ready', 'url': url, 'filename': filename, 'report_type': type_})}\n\n"
                                        reported_urls.add(url)
                    
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
                save_chat_message(thread_id, "assistant", final_ai_msg, metadata={"reasoning": reasoning})

            yield f"data: {json.dumps({'type': 'final_answer', 'response': final_ai_msg, 'reasoning': reasoning, 'thread_id': thread_id})}\n\n"
            
        except Exception as e:
            logger.exception("Streaming error")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat/threads", response_model=ChatThread, tags=["Chat"], summary="Create Chat Thread", description="Initializes a new conversation thread and returns its unique ID.")
async def create_chat_thread(current_user: UserInDB = Depends(get_current_active_user)) -> ChatThread:
    """Creates a new unique chat thread for tracking conversation history."""
    thread_id = str(uuid.uuid4())
    create_thread(thread_id, user_id=current_user.user_id)
    return ChatThread(
        thread_id=thread_id,
        created_at=datetime.utcnow().isoformat() + "Z",
        updated_at=datetime.utcnow().isoformat() + "Z",
        last_message="",
        message_count=0,
    )


@app.get("/chat/threads", response_model=List[ChatThread], tags=["Chat"], summary="List Chat Threads", description="Retrieves a list of all chat threads for the current system.")
async def list_chat_threads(current_user: UserInDB = Depends(get_current_active_user)) -> List[ChatThread]:
    """Lists all available chat threads with their metadata and message counts."""
    rows = get_chat_threads(user_id=current_user.user_id, role=current_user.role)
    return [
        ChatThread(
            thread_id=row["thread_id"],
            created_at=row["created_at"] + ("Z" if "Z" not in row["created_at"] else ""),
            updated_at=row["updated_at"] + ("Z" if "Z" not in row["updated_at"] else ""),
            last_message=row.get("last_message") or "",
            message_count=int(row.get("message_count") or 0),
        )
        for row in rows
    ]


@app.get("/chat/history/{thread_id}", response_model=List[ChatHistoryItem], tags=["Chat"], summary="Get Chat History", description="Retrieves the full message history for a specific conversation thread.")
async def get_chat_history_endpoint(thread_id: str, current_user: UserInDB = Depends(get_current_active_user)) -> List[ChatHistoryItem]:
    """Fetches all previous messages and associated metadata for the given thread ID."""
    if not thread_exists(thread_id, user_id=current_user.user_id, role=current_user.role):
        raise HTTPException(status_code=404, detail="Chat thread not found")
    rows = get_chat_history(thread_id, user_id=current_user.user_id, role=current_user.role)
    return [
        ChatHistoryItem(
            role=row["role"], 
            message=row["message"], 
            timestamp=row["timestamp"],
            metadata=row.get("metadata")
        )
        for row in rows
    ]


@app.post("/kb/documents", tags=["Knowledge"], summary="Ingest Documents", description="Uploads and processes documents for semantic search with user isolation.")
async def ingest_knowledge(
    file: Optional[UploadFile] = File(None),
    content: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    scope: str = Form("global"),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """
    Ingest knowledge from either a text payload or an uploaded file.
    Supports multi-user scoping (Personal, Workspace, Global).
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

        # Use the existing RAG tool logic with scope and user_id
        # 'global' is public, everything else is user-scoped for now
        # We use .invoke() because the function is decorated as a LangChain tool
        result_json = add_documents_to_knowledge_base.invoke({
            "content": final_content, 
            "source": final_source, 
            "scope": scope, 
            "user_id": current_user.user_id if scope != "global" else None,
            "role": current_user.role
        })
        result = json.loads(result_json)

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        return result
    except Exception as e:
        logger.exception("Knowledge ingestion failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/chat/threads/{thread_id}", tags=["Chat"], summary="Delete Chat Thread", description="Permanently deletes a chat thread and all its associated message history.")
async def delete_chat_thread_endpoint(thread_id: str, current_user: UserInDB = Depends(get_current_active_user)):
    """Removes the specified thread and all stored messages from the database."""
    if not thread_exists(thread_id, user_id=current_user.user_id, role=current_user.role):
        raise HTTPException(status_code=404, detail="Chat thread not found")
    delete_chat_thread(thread_id)
    return {"detail": "Chat thread deleted"}


@app.get("/dashboard/projects", tags=["Dashboard"], summary="List Projects", description="Retrieves a list of all active projects for the Pulse dashboard.")
async def get_dashboard_projects(current_user: UserInDB = Depends(get_current_active_user)):
    """Fetch projects for the Pulse page with status and metrics."""
    try:
        return get_all_projects(user_id=current_user.user_id, role=current_user.role)
    except Exception as e:
        logger.error(f"Failed to fetch projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dashboard/projects/{project_id}/timeline", tags=["Dashboard"], summary="Get Project Timeline", description="Retrieves a unified timeline of events, milestones, and updates for a specific project.")
async def get_dashboard_timeline(project_id: str, current_user: UserInDB = Depends(get_current_active_user)):
    """Fetch unified timeline for a project, sorted by date."""
    try:
        return get_project_timeline(project_id, user_id=current_user.user_id, role=current_user.role)
    except Exception as e:
        logger.error(f"Failed to fetch timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dashboard/projects/{project_id}/simulate-full-lifecycle", tags=["Dashboard"], summary="Simulate Project Lifecycle", description="Triggers a simulation that progresses a project through various lifecycle stages.")
async def simulate_project_lifecycle(project_id: str, current_user: UserInDB = Depends(get_current_active_user)):
    """Simulate a project progressing through its lifecycle with user authorization."""
    # In a real app, this would trigger agent actions.
    return {"message": f"Simulation started for project {project_id}"}


@app.get("/dashboard/notifications", tags=["Dashboard"], summary="Get Notifications", description="Retrieves all pending notifications and meeting transcript alerts.")
async def get_dashboard_notifications_endpoint(current_user: UserInDB = Depends(get_current_active_user)):
    """Fetch pending meeting notifications and suggested actions, scoped to user."""
    try:
        return get_pending_notifications(user_id=current_user.user_id, role=current_user.role)
    except Exception as e:
        logger.error(f"Failed to fetch notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dashboard/notifications/{transcript_id}/action", tags=["Dashboard"], summary="Handle Notification Action", description="Applies a specific action (e.g., 'DONE', 'REJECTED') to a pending notification.")
async def handle_notification_action(transcript_id: int, action: str = Body(..., embed=True), current_user: UserInDB = Depends(get_current_active_user)):
    """Handle actions on notifications with security checks."""
    try:
        # Check authorization
        pending = get_pending_notifications(user_id=current_user.user_id, role=current_user.role)
        if not any(n['id'] == transcript_id for n in pending):
             raise HTTPException(status_code=403, detail="Unauthorized access to notification")

        status = "DONE" if action == "make_rfp" else "REJECTED"
        success = update_notification_status(transcript_id, status)
        if not success:
            raise HTTPException(status_code=404, detail="Notification update failed")
        return {"status": "success", "action_taken": action}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process notification action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/chat/suggestions/{thread_id}", tags=["Chat"], summary="Get Chat Suggestions", description="Generates dynamic follow-up questions or suggestions based on the current chat context.")
async def get_chat_suggestions_endpoint(thread_id: str):
    """Fetch dynamic suggestions for the current thread to guide the user."""
    try:
        return get_dynamic_suggestions(thread_id)
    except Exception as e:
        logger.error(f"Failed to fetch suggestions: {e}")
        return ["What is the current status?", "Show latest milestones.", "Check project budget."]


@app.get("/audit/access-gaps", tags=["Audit"], summary="Get Access Gaps", description="Retrieves all detected security access anomalies and redundant permissions.")
async def get_audit_access_gaps(current_user: UserInDB = Depends(get_current_active_user)):
    """Fetch all access gaps for the Access Guard page, scoped by user."""
    try:
        return get_access_gaps(user_id=current_user.user_id, role=current_user.role)
    except Exception as e:
        logger.error(f"Failed to fetch access gaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reports/list", tags=["Reports"], summary="List All Reports")
async def list_reports():
    """Returns a list of all generated reports in the temporary directory."""
    try:
        from core.session import REPORTS_TEMP_DIR
        if not os.path.exists(REPORTS_TEMP_DIR):
            return []
            
        reports = []
        for filename in os.listdir(REPORTS_TEMP_DIR):
            filepath = os.path.join(REPORTS_TEMP_DIR, filename)
            if os.path.isfile(filepath):
                mtime = os.path.getmtime(filepath)
                ext = filename.split('.')[-1].lower()
                report_type = "pdf" if ext == "pdf" else ("excel" if ext in ["xlsx", "csv"] else "image")
                
                reports.append({
                    "filename": filename,
                    "url": f"http://localhost:8000/reports/download/{filename}",
                    "type": report_type,
                    "timestamp": datetime.fromtimestamp(mtime).isoformat()
                })
        
        # Sort by timestamp descending
        reports.sort(key=lambda x: x["timestamp"], reverse=True)
        return reports
    except Exception as e:
        logger.error("Failed to list reports", error=str(e))
        return []

@app.get("/reports/download/{filename}", tags=["Reports"], summary="Download Report", description="Serves a generated report file (Excel, PDF, or image) for download.")
async def download_report(filename: str):
    """
    Serves a generated Excel or image report file.
    Includes security checks to prevent path traversal and unauthorized access.
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
# ========================== Credit Management ==========================

@app.get("/credits/summary", tags=["Credits"])
async def get_credit_summary(current_user: UserInDB = Depends(get_current_active_user)):
    return CreditService.get_summary(current_user.user_id, role=current_user.role)

@app.post("/credits/deduct", tags=["Credits"])
async def deduct_credits(
    request: CreditDeductionRequest,
    current_user: UserInDB = Depends(get_current_active_user)
):
    success = CreditService.deduct_credits(
        current_user.user_id,
        request.project_id,
        request.task_name,
        request.amount
    )
    if not success:
        raise HTTPException(status_code=400, detail="Insufficient credits or invalid request")
    return {"status": "success", "message": f"Deducted {request.amount} credits"}

@app.post("/credits/bill", tags=["Credits"])
async def process_vendor_bill(
    request: VendorBillRequest,
    current_user: UserInDB = Depends(get_current_active_user)
):
    result = CreditService.adjust_vendor_bill(
        current_user.user_id,
        request.vendor_id,
        request.project_id,
        request.total_amount
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to process vendor bill")
    return result

@app.post("/credits/close-year", tags=["Credits"])
async def close_year(current_user: UserInDB = Depends(get_current_active_user)):
    success = CreditService.close_financial_year(current_user.user_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to close financial year")
    return {"status": "success", "message": "Financial year closed and credits carried forward"}
