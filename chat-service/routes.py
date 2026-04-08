from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from openai import OpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
import os
import time
import random
from typing import cast, Literal

from shared.database import db_dependency
from .schemas import (
    ChatIn,
    ChatOut,
    ConversationCreateOut,
    ConversationOut,
    MessageOut,
)
from .crud import (
    save_message,
    recent_messages,
    create_conversation,
    get_conversation,
    list_conversations,
    delete_conversation,
    delete_recent_conversation,
)
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()


def get_or_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not set")

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://learners-ai.vercel.app"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "course-reco-chat-service"),
        },
    )


def call_with_backoff(fn, max_retries: int = 5):
    base = 0.5
    for attempt in range(max_retries):
        try:
            return fn()
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            time.sleep(min(15.0, base * (2 ** attempt)) + random.uniform(0, 0.25))


def build_router(SessionLocal):
    get_db = db_dependency(SessionLocal)

    def current_user_id(request: Request) -> int:
        uid = request.headers.get("X-User-ID")
        if not uid:
            raise HTTPException(status_code=401, detail="Missing X-User-ID header")
        try:
            return int(uid)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid X-User-ID header")

    def ensure_conversation(db: Session, uid: int, conversation_id: int):
        convo = get_conversation(db, uid, conversation_id)
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return convo

    # ✅ IMPROVED MESSAGE BUILDER
    def build_messages(
        db: Session,
        uid: int,
        conversation_id: int,
        limit: int = 50,  # 🔥 increased memory
        extra_system: str | None = None,
    ):
        history = list(
            reversed(
                recent_messages(
                    db,
                    uid,
                    conversation_id=conversation_id,
                    limit=limit,
                )
            )
        )

        # 🔥 NEW POWERFUL PROMPT
        system_prompt = (
            "You are a highly intelligent, helpful, and expressive AI assistant. "
            "Your goal is to provide clear, detailed, and well-structured answers.\n\n"

            "Response guidelines:\n"
            "- Always respond in multiple paragraphs (minimum 2–4 paragraphs when appropriate).\n"
            "- Expand your explanation naturally depending on the complexity of the question.\n"
            "- Do NOT give overly short or one-line answers.\n"
            "- Provide examples, explanations, and context whenever helpful.\n"
            "- For simple questions, give a slightly expanded explanation.\n"
            "- For complex questions, provide deep, structured, and insightful answers.\n"
            "- Maintain a natural, human-like conversational tone.\n"
            "- Avoid unnecessary repetition, but do not limit response length artificially.\n"
            "- Prioritize clarity, depth, and usefulness.\n\n"

            "Structure:\n"
            "- Start with a clear answer.\n"
            "- Follow with explanation.\n"
            "- Add examples if needed.\n"
            "- End with helpful insight or summary."
        )

        if extra_system:
            system_prompt += " " + extra_system

        msgs = [{"role": "system", "content": system_prompt}]

        for m in history:
            if m.role in ("user", "assistant") and m.content:
                msgs.append({"role": m.role, "content": m.content})

        return cast(list[ChatCompletionMessageParam], msgs)

    # ✅ IMPROVED LLM CALL
    def call_llm(db: Session, uid: int, conversation_id: int) -> str:
        client = get_or_client()
        model = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.6-plus:free")

        input_messages = build_messages(db, uid, conversation_id, limit=10)

        try:
            resp = call_with_backoff(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=input_messages,
                    max_tokens=1000,  # 🔥 longer responses
                    temperature=0.5,  # 🔥 more natural
                )
            )

            if resp and hasattr(resp, "choices") and resp.choices:
                reply = (resp.choices[0].message.content or "").strip()
            else:
                reply = ""

            return reply or "Sorry—I'm having trouble generating a response right now."

        except RateLimitError:
            raise HTTPException(
                status_code=429,
                detail="Rate limited. Please retry in a few seconds.",
            )
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"LLM provider error: {type(e).__name__}",
            )

    # ================= ROUTES =================

    @router.post("/conversations", response_model=ConversationCreateOut)
    def create_new_conversation(request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)
        convo = create_conversation(db, uid)
        return ConversationCreateOut(id=convo.id, title=convo.title)

    @router.get("/conversations", response_model=list[ConversationOut])
    def get_conversations(request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)
        convos = list_conversations(db, uid, limit=50)
        return [
            ConversationOut(
                id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in convos
        ]

    @router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
    def get_conversation_messages(
        conversation_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        uid = current_user_id(request)
        ensure_conversation(db, uid, conversation_id)

        msgs = recent_messages(db, uid, conversation_id=conversation_id, limit=100)
        return [MessageOut(role=cast(Literal["user", "assistant"], m.role), content=m.content, created_at=m.created_at) for m in reversed(msgs)]

    @router.post("/conversations/{conversation_id}", response_model=ChatOut)
    def chat_in_conversation(
        conversation_id: int,
        payload: ChatIn,
        request: Request,
        db: Session = Depends(get_db),
    ):
        uid = current_user_id(request)
        ensure_conversation(db, uid, conversation_id)

        save_message(db, uid, conversation_id, "user", payload.message)
        reply = call_llm(db, uid, conversation_id)
        save_message(db, uid, conversation_id, "assistant", reply)

        return ChatOut(reply=reply)

    @router.post("/", response_model=ChatOut)
    def chat(payload: ChatIn, request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)

        convo = create_conversation(db, uid)
        save_message(db, uid, convo.id, "user", payload.message)
        reply = call_llm(db, uid, convo.id)
        save_message(db, uid, convo.id, "assistant", reply)

        return ChatOut(reply=reply)

    @router.get("/recent", response_model=list[MessageOut])
    def recent(request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)
        convos = list_conversations(db, uid, limit=1)

        if not convos:
            return []

        latest = convos[0]
        msgs = recent_messages(db, uid, conversation_id=latest.id, limit=20)
        return [MessageOut(role=cast(Literal["user", "assistant"], m.role), content=m.content, created_at=m.created_at) for m in reversed(msgs)]

    @router.delete("/recent")
    def delete_recent(request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)
        deleted = delete_recent_conversation(db, uid)

        if not deleted:
            raise HTTPException(status_code=404, detail="No recent conversation found")

        return {"message": "Recent conversation deleted successfully"}

    @router.delete("/conversations/{conversation_id}")
    def delete_one_conversation(
        conversation_id: int,
        request: Request,
        db: Session = Depends(get_db),
    ):
        uid = current_user_id(request)
        deleted = delete_conversation(db, uid, conversation_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return {"message": "Conversation deleted successfully"}

    return router