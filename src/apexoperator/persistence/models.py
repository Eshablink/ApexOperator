from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TaskRecord(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        String(64),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        nullable=False,
    )


class TaskEvidenceRecord(Base):
    __tablename__ = "task_evidence"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    planner_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    planner_model: Mapped[str | None] = mapped_column(String(128))
    planner_fallback: Mapped[bool] = mapped_column(default=False, nullable=False)
    proposals: Mapped[Any] = mapped_column(JSON, nullable=False)
    policy_decision: Mapped[Any | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(
        String(64),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        nullable=False,
    )


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    sequence_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    after_state: Mapped[Any] = mapped_column(JSON, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class AuditLedgerMeta(Base):
    __tablename__ = "audit_ledger_meta"

    singleton: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    head_sequence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    head_event_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class UserRecord(Base):
    __tablename__ = "users"

    actor_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[str] = mapped_column(
        String(64),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        nullable=False,
    )


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revoked_at: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(
        String(64),
        default=lambda: datetime.now(timezone.utc).isoformat(),
        nullable=False,
    )
