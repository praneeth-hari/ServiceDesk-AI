from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class AIAssistStatusResponse(BaseModel):
    enabled: bool
    mode: Literal["off", "ollama"]
    model: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AIAssistRequest(BaseModel):
    task: Literal["summary", "reply"]


class AIAssistFact(BaseModel):
    label: str = Field(..., max_length=30)
    value: str = Field(..., max_length=80)

    model_config = ConfigDict(from_attributes=True)


class AIAssistSummaryResponse(BaseModel):
    task: Literal["summary"] = "summary"
    summary: str = Field(..., max_length=600)
    facts: list[AIAssistFact] = Field(default_factory=list, max_length=4)
    model: str
    latency_ms: int

    model_config = ConfigDict(from_attributes=True)


class AIAssistReplyResponse(BaseModel):
    task: Literal["reply"] = "reply"
    reply: str = Field(..., max_length=1200)
    model: str
    latency_ms: int

    model_config = ConfigDict(from_attributes=True)
