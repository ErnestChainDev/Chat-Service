from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatOut(BaseModel):
    reply: str


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

    model_config = ConfigDict(from_attributes=True)

class MessageOut(BaseModel):
    role: str
    content: str

    model_config = ConfigDict(from_attributes=True)