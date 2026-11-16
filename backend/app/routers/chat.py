import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_account
from app.models.admin import Admin
from app.models.chat import ChatConversation, ChatMessage
from app.schemas.chat import ChatMessageRequest
from app.services.chatbot import (
    build_database_context,
    deterministic_chat_reply,
    generate_chat_reply,
)

router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


def _serialize_message(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
    }


@router.get("/conversation")
def get_current_conversation(
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_account),
):
    conversation = (
        db.query(ChatConversation)
        .filter(ChatConversation.account_id == account.id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        .first()
    )
    if conversation is None:
        return {"conversation_id": None, "messages": []}
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.id.desc())
        .limit(50)
        .all()
    )
    return {
        "conversation_id": conversation.id,
        "messages": [
            _serialize_message(message) for message in reversed(messages)
        ],
    }


@router.post("/messages")
def send_message(
    body: ChatMessageRequest,
    db: Session = Depends(get_db),
    account: Admin = Depends(get_current_account),
):
    content = body.message.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    if body.conversation_id is None:
        conversation = ChatConversation(account_id=account.id)
        db.add(conversation)
        db.flush()
    else:
        conversation = db.query(ChatConversation).filter(
            ChatConversation.id == body.conversation_id,
            ChatConversation.account_id == account.id,
        ).first()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    prior_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.id.desc())
        .limit(12)
        .all()
    )
    history: list[dict[str, str]] = [
        {
            "role": getattr(message, "role"),
            "content": getattr(message, "content"),
        }
        for message in reversed(prior_messages)
    ]
    history.append({"role": "user", "content": content})

    context_query = content
    previous_user_message = next(
        (
            getattr(message, "content")
            for message in reversed(prior_messages)
            if getattr(message, "role") == "user"
        ),
        None,
    )
    is_follow_up = re.search(
        r"\b(?:it|that|those|them|one|another|other|similar|cheaper|"
        r"what about|when|where|arrive|status|also|and)\b",
        content.casefold(),
    )
    if previous_user_message and is_follow_up:
        context_query = f"{previous_user_message}\n{content}"
    context = build_database_context(db, account, context_query)
    reply = deterministic_chat_reply(account, content, context)
    if reply is None:
        reply = generate_chat_reply(account, history, context)

    user_message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=reply,
    )
    setattr(conversation, "updated_at", datetime.now(timezone.utc))
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return {
        "conversation_id": conversation.id,
        "user_message": _serialize_message(user_message),
        "assistant_message": _serialize_message(assistant_message),
    }
