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
    comment: str | None = None


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
