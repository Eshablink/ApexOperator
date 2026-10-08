from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(str, Enum):
    RUNNING = "RUNNING"
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_HUMAN_APPROVAL = "PENDING_HUMAN_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: str
    justification: str | None = None
    planner_mode: Literal["mock", "openai"] | None = None

    @field_validator("invoice_id")
    @classmethod
    def validate_invoice_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("invoice_id cannot be empty")
        return value

    @field_validator("justification")
    @classmethod
    def validate_justification(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field(min_length=3, max_length=1000)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("review reason must be at least 3 characters")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or len(value) > 320:
            raise ValueError("valid email is required")
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 12:
            raise ValueError("password must be at least 12 characters")
        return value


class TaskResponse(BaseModel):
    task_id: str
    invoice_id: str
    status: TaskStatus
    requested_by: str
    decision: str
    justification: str | None = None
    reviewer: str | None = None
    review_comment: str | None = None


class PlannerProposalResponse(BaseModel):
    step: int
    tool_name: str
    input_data: dict[str, Any]


class TaskAuditEventResponse(BaseModel):
    sequence_id: int
    event_id: str
    timestamp: str
    event_type: str
    action: str
    after_state: dict[str, Any]
    previous_hash: str
    event_hash: str


class TaskDetailResponse(BaseModel):
    task: TaskResponse
    planner: dict[str, Any]
    audit_timeline: list[TaskAuditEventResponse]


class AuditVerificationResponse(BaseModel):
    integrity_valid: bool
