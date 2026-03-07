from datetime import datetime
from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatOut(BaseModel):
    reply: str


class ConversationCreateOut(BaseModel):
    id: int
    title: str


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    role: str
    content: str