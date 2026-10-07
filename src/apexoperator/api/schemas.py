from enum import Enum

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

    @field_validator("invoice_id")
    @classmethod
    def validate_invoice_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("invoice_id cannot be empty")
        return value


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(default=None, max_length=1000)


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


class AuditVerificationResponse(BaseModel):
    integrity_valid: bool
