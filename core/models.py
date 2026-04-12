"""
SQLAlchemy Models - Database schema for AMM
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


def generate_uuid() -> str:
    """Generate a new UUID string"""
    return str(uuid.uuid4())


# Enums
class SignalStatus(str, enum.Enum):
    RAW = "raw"
    EVALUATED = "evaluated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, enum.Enum):
    CODING = "coding"
    CONTENT = "content"
    DESIGN = "design"
    MARKETING = "marketing"
    RESEARCH = "research"
    HUMAN = "human"


class ExecutionType(str, enum.Enum):
    AUTO = "auto"
    SEMI = "semi"
    MANUAL = "manual"


class Priority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class HumanTaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class SkillStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class Urgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Models
class Signal(Base):
    """Business opportunity signal discovered by scouts"""
    
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(50), nullable=False, index=True)  # upwork, fiverr, github, etc.
    scout_type = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    estimated_revenue = Column(Float)
    estimated_effort_hours = Column(Float)
    urgency = Column(String(20), default=Urgency.MEDIUM)
    required_skills = Column(JSON, default=list)
    raw_url = Column(String(1000))
    score = Column(Float, nullable=True)  # Evaluation score
    status = Column(String(20), default=SignalStatus.RAW, index=True)
    requires_human_interaction = Column(Boolean, default=True)
    compliance_flags = Column(JSON, default=list)
    meta_data = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tasks = None  # Will be set by backref
    
    __table_args__ = (
        Index('ix_signals_status_created_at', 'status', 'created_at'),
        Index('ix_signals_source_scout_type', 'source', 'scout_type'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "source": self.source,
            "scout_type": self.scout_type,
            "title": self.title,
            "description": self.description,
            "estimated_revenue": self.estimated_revenue,
            "estimated_effort_hours": self.estimated_effort_hours,
            "urgency": self.urgency,
            "required_skills": self.required_skills,
            "raw_url": self.raw_url,
            "score": self.score,
            "status": self.status,
            "requires_human_interaction": self.requires_human_interaction,
            "compliance_flags": self.compliance_flags,
            "metadata": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Signal":
        return cls(
            id=uuid.UUID(data["id"]) if "id" in data else uuid.uuid4(),
            source=data["source"],
            scout_type=data["scout_type"],
            title=data["title"],
            description=data.get("description"),
            estimated_revenue=data.get("estimated_revenue"),
            estimated_effort_hours=data.get("estimated_effort_hours"),
            urgency=data.get("urgency", Urgency.MEDIUM),
            required_skills=data.get("required_skills", []),
            raw_url=data.get("raw_url"),
            score=data.get("score"),
            status=data.get("status", SignalStatus.RAW),
            requires_human_interaction=data.get("requires_human_interaction", True),
            compliance_flags=data.get("compliance_flags", []),
            meta_data=data.get("metadata", {}),
        )


class Task(Base):
    """Task created from accepted signals"""
    
    __tablename__ = "tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id"), nullable=True)
    parent_task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    title = Column(String(500))
    task_type = Column(String(50), index=True)  # coding, content, design, etc.
    execution_type = Column(String(20), default=ExecutionType.MANUAL)  # auto, semi, manual
    status = Column(String(20), default=TaskStatus.PENDING, index=True)
    priority = Column(String(20), default=Priority.NORMAL)
    assigned_worker = Column(String(50), nullable=True)
    skill_id = Column(String(100), nullable=True)
    input_data = Column(JSON, default=dict)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=True)
    depends_on = Column(JSON, default=list)  # List of task IDs
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_tasks_signal_id', 'signal_id'),
        Index('ix_tasks_status_task_type', 'status', 'task_type'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "signal_id": str(self.signal_id) if self.signal_id else None,
            "parent_task_id": str(self.parent_task_id) if self.parent_task_id else None,
            "title": self.title,
            "task_type": self.task_type,
            "execution_type": self.execution_type,
            "status": self.status,
            "priority": self.priority,
            "assigned_worker": self.assigned_worker,
            "skill_id": self.skill_id,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "depends_on": self.depends_on,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        signal_id = data.get("signal_id")
        parent_task_id = data.get("parent_task_id")
        
        return cls(
            id=uuid.UUID(data["id"]) if "id" in data else uuid.uuid4(),
            signal_id=uuid.UUID(signal_id) if signal_id else None,
            parent_task_id=uuid.UUID(parent_task_id) if parent_task_id else None,
            title=data.get("title"),
            task_type=data.get("task_type"),
            execution_type=data.get("execution_type", ExecutionType.MANUAL),
            status=data.get("status", TaskStatus.PENDING),
            priority=data.get("priority", Priority.NORMAL),
            assigned_worker=data.get("assigned_worker"),
            skill_id=data.get("skill_id"),
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data"),
            error_message=data.get("error_message"),
            estimated_cost=data.get("estimated_cost"),
            actual_cost=data.get("actual_cost"),
            depends_on=data.get("depends_on", []),
        )


class TaskResult(Base):
    """Result of task execution"""
    
    __tablename__ = "task_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    status = Column(String(20), nullable=False)  # completed, failed
    output_data = Column(JSON, default=dict)
    files_generated = Column(JSON, default=list)
    ai_calls_count = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    execution_time = Column(Float)  # seconds
    quality_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "status": self.status,
            "output_data": self.output_data,
            "files_generated": self.files_generated,
            "ai_calls_count": self.ai_calls_count,
            "total_cost": self.total_cost,
            "execution_time": self.execution_time,
            "quality_notes": self.quality_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class HumanTask(Base):
    """Human intervention tasks"""
    
    __tablename__ = "human_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    task_type = Column(String(100), nullable=False)  # submit_proposal, deliver_files, etc.
    platform = Column(String(50))
    priority = Column(String(20), default=Priority.NORMAL)
    status = Column(String(20), default=HumanTaskStatus.PENDING)
    prepared_materials = Column(JSON, default=dict)
    instructions = Column(Text)
    target_url = Column(String(1000), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(100), nullable=True)
    completion_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index('ix_human_tasks_status_priority', 'status', 'priority'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "task_type": self.task_type,
            "platform": self.platform,
            "priority": self.priority,
            "status": self.status,
            "prepared_materials": self.prepared_materials,
            "instructions": self.instructions,
            "target_url": self.target_url,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "completed_by": self.completed_by,
            "completion_notes": self.completion_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "HumanTask":
        return cls(
            id=uuid.UUID(data["id"]) if "id" in data else uuid.uuid4(),
            task_id=uuid.UUID(data["task_id"]),
            task_type=data["task_type"],
            platform=data.get("platform"),
            priority=data.get("priority", Priority.NORMAL),
            status=data.get("status", HumanTaskStatus.PENDING),
            prepared_materials=data.get("prepared_materials", {}),
            instructions=data.get("instructions"),
            target_url=data.get("target_url"),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            completed_by=data.get("completed_by"),
            completion_notes=data.get("completion_notes"),
        )


class Skill(Base):
    """Skill definitions for reusable workflows"""
    
    __tablename__ = "skills"
    
    id = Column(String(100), primary_key=True)  # e.g., "upwork-python-cli"
    name = Column(String(200), nullable=False)
    version = Column(String(20), default="1.0")
    category = Column(String(100))
    status = Column(String(20), default=SkillStatus.DRAFT)
    success_rate = Column(Float, default=0.0)
    avg_revenue = Column(Float, default=0.0)
    avg_ai_cost = Column(Float, default=0.0)
    avg_time_hours = Column(Float, default=0.0)
    execution_count = Column(Integer, default=0)
    triggers = Column(JSON, default=dict)  # Matching rules
    compliance = Column(JSON, default=dict)
    workflow = Column(JSON, default=dict)  # Workflow definition
    quality_checklist = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "status": self.status,
            "success_rate": self.success_rate,
            "avg_revenue": self.avg_revenue,
            "avg_ai_cost": self.avg_ai_cost,
            "avg_time_hours": self.avg_time_hours,
            "execution_count": self.execution_count,
            "triggers": self.triggers,
            "compliance": self.compliance,
            "workflow": self.workflow,
            "quality_checklist": self.quality_checklist,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0"),
            category=data.get("category"),
            status=data.get("status", SkillStatus.DRAFT),
            success_rate=data.get("success_rate", 0.0),
            avg_revenue=data.get("avg_revenue", 0.0),
            avg_ai_cost=data.get("avg_ai_cost", 0.0),
            avg_time_hours=data.get("avg_time_hours", 0.0),
            execution_count=data.get("execution_count", 0),
            triggers=data.get("triggers", {}),
            compliance=data.get("compliance", {}),
            workflow=data.get("workflow", {}),
            quality_checklist=data.get("quality_checklist", []),
        )


class CostRecord(Base):
    """AI cost tracking records"""
    
    __tablename__ = "cost_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    model_tier = Column(String(20), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost = Column(Float, nullable=False)
    latency_ms = Column(Integer)
    cached = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_cost_records_created_at', 'created_at'),
        Index('ix_cost_records_task_id', 'task_id'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "task_id": str(self.task_id) if self.task_id else None,
            "provider": self.provider,
            "model": self.model,
            "model_tier": self.model_tier,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    """Audit logs for all system activities"""
    
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(100), nullable=False, index=True)
    actor = Column(String(100), nullable=False)  # system, human, agent_name
    details = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_audit_logs_event_type_created_at', 'event_type', 'created_at'),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "actor": self.actor,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AuditLog":
        return cls(
            id=uuid.UUID(data["id"]) if "id" in data else uuid.uuid4(),
            event_type=data["event_type"],
            actor=data["actor"],
            details=data.get("details", {}),
        )
