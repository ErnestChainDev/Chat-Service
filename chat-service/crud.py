from sqlalchemy.orm import Session
from .models import ChatMessage, ChatConversation


def create_conversation(db: Session, user_id: int, title: str = "New Chat"):
    convo = ChatConversation(user_id=user_id, title=title)
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


def get_conversation(db: Session, user_id: int, conversation_id: int):
    return (
        db.query(ChatConversation)
        .filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
        .first()
    )


def list_conversations(db: Session, user_id: int, limit: int = 20):
    return (
        db.query(ChatConversation)
        .filter(ChatConversation.user_id == user_id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        .limit(limit)
        .all()
    )


def save_message(db: Session, user_id: int, conversation_id: int, role: str, content: str):
    m = ChatMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    db.add(m)

    convo = (
        db.query(ChatConversation)
        .filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
        .first()
    )
    if convo:
        from datetime import datetime
        convo.updated_at = datetime.utcnow()

        if convo.title == "New Chat" and role == "user":
            trimmed = content.strip()
            convo.title = trimmed[:60] if trimmed else "New Chat"

    db.commit()
    db.refresh(m)
    return m


def recent_messages(db: Session, user_id: int, conversation_id: int, limit: int = 10):
    q = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
        )
    )

    if hasattr(ChatMessage, "created_at"):
        q = q.order_by(ChatMessage.created_at.desc())  # type: ignore
    else:
        q = q.order_by(ChatMessage.id.desc())

    return q.limit(limit).all()