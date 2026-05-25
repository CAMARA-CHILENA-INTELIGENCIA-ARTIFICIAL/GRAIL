"""
Pydantic models for the GRAIL chat API.

Provided by Nirvai (Nirvana). Author: Benjamin González Guerrero.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ Auth


class AuthRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)


class UserResponse(BaseModel):
    id: str
    username: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ------------------------------------------------------------------ Sessions


class SessionCreate(BaseModel):
    title: str = "New Chat"
    mode: str = "local"


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    mode: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    title: str
    mode: str
    created_at: str
    updated_at: str
    message_count: int = 0


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    mode: str
    created_at: str
    updated_at: str
    messages: list[MessageResponse] = Field(default_factory=list)


# ------------------------------------------------------------------ Chat


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)
    mode: Optional[str] = None
    document: Optional[str] = None
    use_reranker: Optional[bool] = None


# ------------------------------------------------------------------ Config


class ConfigResponse(BaseModel):
    project_name: str
    project_path: str
    modes: list[str]
    has_reranker: bool
    version: str
