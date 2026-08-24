from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Literal

class Document(BaseModel):
    content: str
    metadata: dict[str, Any]
    source_file: str

class Chunk(BaseModel):
    id: str
    text: str
    source_file: str
    heading: str
    document_id: str | None = None
    status: Literal["active", "superseded","draft"] = "active"
    policy_authority: str | None = None      # "official" or None/other
    superseded_by: str | None = None          # document_id of replacing doc, if any
    doc_title: str | None = None
    audience: str | None = None
    customer_answering: bool = True

class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float


 
class OrderItem(BaseModel):
 
    name: str
    quantity: int
    final_sale: bool
 
 
class OrderLookupResult(BaseModel):
   
    order_id: str
    found: bool
    membership_tier: str | None = None
    items: list[OrderItem] | None = None
    placed_at: str | None = None
    status: str | None = None
    status_updated_at: str | None = None
    shipped_at: str | None = None
    delivered_at: str | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    estimated_delivery: str | None = None
    customer_safe_message: str | None = None
    error: Literal["not_found", "malformed_id"] | None = None
    handoff_required: bool = False
    handoff_reason: str | None = None
 
 

 
class ToolCall(BaseModel):
 
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    called_at: datetime = Field(default_factory=datetime.utcnow)
 

 
class TraceEvent(BaseModel):
    session_id: str
    turn_index: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
 
    user_message: str
    conversation_history: list[dict[str, str]]  # [{"role": ..., "content": ...}, ...]
 
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
 
    final_response: str
    sources_cited: list[str] = Field(default_factory=list)  # e.g. ["01-returns-policy-current.md#standard-return-window"]
 
    handoff: bool = False
    handoff_reason: str | None = None
 
    error: str | None = None