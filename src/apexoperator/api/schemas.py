from enum import Enum
from typing import Literal

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


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(default=None, min_length=3, max_length=500)

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("review reason cannot be empty")
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


class TaskDetailResponse(TaskResponse):
    audit_timeline: list[dict] = Field(default_factory=list)
    planner_proposals: list[dict] = Field(default_factory=list)
    policy_decision: str | None = None


class AuditVerificationResponse(BaseModel):
    integrity_valid: bool
