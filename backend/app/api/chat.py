import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Message, PromptVersion, Session

router = APIRouter(prefix="/api/chat", tags=["chat"])


class CreateSessionRequest(BaseModel):
    title: str = "New Chat"


class SendMessageRequest(BaseModel):
    session_id: str
    message: str


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    tool_calls: dict | list | None = None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).order_by(Session.updated_at.desc()))
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.post("/sessions", response_model=SessionResponse)
async def create_session(req: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    session = Session(title=req.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        MessageResponse(
            id=m.id,
            session_id=m.session_id,
            role=m.role,
            content=m.content,
            tool_calls=m.tool_calls,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("/stream")
async def stream_chat(req: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    """Stream agent response via SSE."""
    from app.agent.graph import stream_agent

    # Verify session exists
    result = await db.execute(select(Session).where(Session.id == req.session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save user message
    user_msg = Message(
        session_id=req.session_id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.commit()

    # Load message history
    msg_result = await db.execute(
        select(Message).where(Message.session_id == req.session_id).order_by(Message.created_at)
    )
    history = msg_result.scalars().all()
    messages = [{"role": m.role, "content": m.content} for m in history]

    # Get active prompt version
    prompt_result = await db.execute(
        select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
    )
    active_prompt = prompt_result.scalar_one_or_none()
    system_prompt = active_prompt.content if active_prompt else None

    # Capture values needed for the stream closure
    session_id = req.session_id
    user_message_text = req.message
    history_len = len(history)

    async def event_stream():
        accumulated_content = ""
        tool_calls_data = []

        try:
            async for event in stream_agent(messages, system_prompt):
                if event["type"] == "content":
                    accumulated_content += event["content"]
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "tool_call":
                    tool_calls_data.append(
                        {
                            "id": f"tc_{len(tool_calls_data)}",
                            "name": event["name"],
                            "input": event.get("input", {}),
                        }
                    )
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "tool_result":
                    # Attach output to last tool call
                    if tool_calls_data:
                        tool_calls_data[-1]["output"] = event.get("output", "")
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "done":
                    # Save assistant message to DB
                    async with await _get_new_session() as save_db:
                        assistant_msg = Message(
                            session_id=session_id,
                            role="assistant",
                            content=accumulated_content,
                            tool_calls=tool_calls_data if tool_calls_data else None,
                        )
                        save_db.add(assistant_msg)

                        # Update session title if first message
                        if history_len <= 1:
                            title_result = await save_db.execute(
                                select(Session).where(Session.id == session_id)
                            )
                            sess = title_result.scalar_one_or_none()
                            if sess:
                                sess.title = user_message_text[:50]
                                sess.updated_at = datetime.now(timezone.utc)

                        await save_db.commit()

                    yield f"data: {json.dumps(event)}\n\n"
                    yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _get_new_session():
    """Get a new DB session for saving within the stream."""
    from app.database import async_session

    return async_session()
