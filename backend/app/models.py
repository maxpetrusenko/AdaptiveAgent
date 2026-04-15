import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String, default="New Chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String)  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    session: Mapped["Session"] = relationship(back_populates="messages")


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String)
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    tags: Mapped[dict] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String, default="manual")  # manual, generated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    results: Mapped[list["EvalResult"]] = relationship(back_populates="eval_case")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("prompt_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    eval_runs: Mapped[list["EvalRun"]] = relationship(back_populates="prompt_version")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    prompt_version_id: Mapped[str] = mapped_column(
        String, ForeignKey("prompt_versions.id")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String, default="running"
    )  # running, completed, failed
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

    prompt_version: Mapped["PromptVersion"] = relationship(back_populates="eval_runs")
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="eval_run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    eval_run_id: Mapped[str] = mapped_column(String, ForeignKey("eval_runs.id"))
    eval_case_id: Mapped[str] = mapped_column(String, ForeignKey("eval_cases.id"))
    status: Mapped[str] = mapped_column(String)  # pass, fail, error
    actual_output: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    eval_run: Mapped["EvalRun"] = relationship(back_populates="results")
    eval_case: Mapped["EvalCase"] = relationship(back_populates="results")


class AdaptationRun(Base):
    __tablename__ = "adaptation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String, default="running"
    )  # running, completed, failed, rejected
    before_version_id: Mapped[str] = mapped_column(
        String, ForeignKey("prompt_versions.id")
    )
    after_version_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("prompt_versions.id"), nullable=True
    )
    before_pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    after_pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
