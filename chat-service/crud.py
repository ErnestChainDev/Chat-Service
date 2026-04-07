from datetime import datetime, timezone

from sqlalchemy.orm import Session
from .models import ChatMessage, ChatConversation


def create_conversation(db: Session, user_id: int, title: str = "New Chat"):
    convo = ChatConversation(user_id=user_id, title=title)
    db.add(convo)
    try:
        db.commit()
        db.refresh(convo)
        return convo
    except Exception:
        db.rollback()
        raise


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


def save_message(
    db: Session,
    user_id: int,
    conversation_id: int,
    role: str,
    content: str,
):
    m = ChatMessage(
        user_id=user_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    db.add(m)

    # ✅ faster fetch
    convo = db.get(ChatConversation, conversation_id)

    if convo and convo.user_id == user_id:
        convo.updated_at = datetime.now(timezone.utc)

        if convo.title == "New Chat" and role == "user":
            trimmed = content.strip()
            convo.title = trimmed.split("\n")[0][:60] if trimmed else "New Chat"

    try:
        db.commit()
        db.refresh(m)
        return m
    except Exception:
        db.rollback()
        raise


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


def delete_conversation(db: Session, user_id: int, conversation_id: int) -> bool:
    convo = (
        db.query(ChatConversation)
        .filter(
            ChatConversation.id == conversation_id,
            ChatConversation.user_id == user_id,
        )
        .first()
    )
    if not convo:
        return False

    try:
        db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
        ).delete(synchronize_session=False)

        db.delete(convo)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise


def delete_recent_conversation(db: Session, user_id: int) -> bool:
    convo = (
        db.query(ChatConversation)
        .filter(ChatConversation.user_id == user_id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        .first()
    )

    if not convo:
        return False

    try:
        db.query(ChatMessage).filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == convo.id,
        ).delete(synchronize_session=False)

        db.delete(convo)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise