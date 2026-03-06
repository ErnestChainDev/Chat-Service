import os
import random
import time
from typing import cast

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from openai import OpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
from sqlalchemy.orm import Session

from shared.database import db_dependency
from .crud import recent_messages, save_message
from .schemas import ChatIn, ChatOut

load_dotenv()


def get_or_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not set")

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
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
    router = APIRouter()
    get_db = db_dependency(SessionLocal)

    def current_user_id(request: Request) -> int:
        user = getattr(request.state, "user", None)
        if not user or "sub" not in user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            return int(user["sub"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Invalid user identity")

    def build_messages(
        db: Session,
        uid: int,
        user_text: str,
        limit: int = 12,
        extra_system: str | None = None,
    ) -> list[ChatCompletionMessageParam]:
        history = list(reversed(recent_messages(db, uid, limit=limit)))

        system_prompt = (
            "You are a helpful AI chat assistant. "
            "Be concise, correct, and ask at most one clarifying question when needed."
        )

        if extra_system:
            system_prompt += f" {extra_system}"

        msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        for m in history:
            if m.role in ("user", "assistant") and m.content:
                msgs.append({"role": m.role, "content": m.content})

        msgs.append({"role": "user", "content": user_text})
        return cast(list[ChatCompletionMessageParam], msgs)

    def call_llm(db: Session, uid: int, user_text: str) -> str:
        client = get_or_client()
        model = os.getenv("OPENROUTER_MODEL", "liquid/lfm-2.5-1.2b-thinking:free")
        input_messages = build_messages(db, uid, user_text, limit=10)

        try:
            resp = call_with_backoff(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=input_messages,
                )
            )

            if resp is not None and getattr(resp, "choices", None):
                reply = (resp.choices[0].message.content or "").strip()
            else:
                reply = ""

            return reply or "Sorry—I'm having trouble generating a response right now."

        except RateLimitError:
            raise HTTPException(status_code=429, detail="Rate limited. Please retry in a few seconds.")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM provider error: {type(e).__name__}: {str(e)}")

    @router.post("/", response_model=ChatOut)
    def chat(payload: ChatIn, request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)

        save_message(db, uid, "user", payload.message)
        reply = call_llm(db, uid, payload.message)
        save_message(db, uid, "assistant", reply)

        return ChatOut(reply=reply)

    @router.get("/recent", response_model=list[dict])
    def recent(request: Request, db: Session = Depends(get_db)):
        uid = current_user_id(request)
        msgs = recent_messages(db, uid, limit=20)
        return [{"role": m.role, "content": m.content} for m in reversed(msgs)]

    return router