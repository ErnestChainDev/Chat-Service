from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ChatIn(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User message input",
    )


class ChatOut(BaseModel):
    reply: str
    tokens_used: int | None = None


class ConversationCreateOut(BaseModel):
    id: int
    title: str

    model_config = ConfigDict(from_attributes=True)


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeleteOut(BaseModel):
    message: str


class MessageOut(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)