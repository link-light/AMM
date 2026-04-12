"""
Initial Migration

Create all tables for AI Money Machine Phase 1.

Revision ID: 001
Revises: 
Create Date: 2026-04-12 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema"""
    
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create signals table
    op.create_table(
        'signals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('scout_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('estimated_revenue', sa.Float(), nullable=True),
        sa.Column('estimated_effort_hours', sa.Float(), nullable=True),
        sa.Column('urgency', sa.String(20), server_default='medium'),
        sa.Column('required_skills', postgresql.JSONB(), server_default='[]'),
        sa.Column('raw_url', sa.String(1000), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), server_default='raw', index=True),
        sa.Column('requires_human_interaction', sa.Boolean(), server_default='true'),
        sa.Column('compliance_flags', postgresql.JSONB(), server_default='[]'),
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Create indexes for signals
    op.create_index('ix_signals_status_created_at', 'signals', ['status', 'created_at'])
    op.create_index('ix_signals_source_scout_type', 'signals', ['source', 'scout_type'])
    op.create_index('ix_signals_source', 'signals', ['source'])
    op.create_index('ix_signals_scout_type', 'signals', ['scout_type'])
    
    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('signal_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('signals.id'), nullable=True),
        sa.Column('parent_task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('task_type', sa.String(50), nullable=True, index=True),
        sa.Column('execution_type', sa.String(20), server_default='manual'),
        sa.Column('status', sa.String(20), server_default='pending', index=True),
        sa.Column('priority', sa.String(20), server_default='normal'),
        sa.Column('assigned_worker', sa.String(50), nullable=True),
        sa.Column('skill_id', sa.String(100), nullable=True),
        sa.Column('input_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('output_data', postgresql.JSONB(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('estimated_cost', sa.Float(), nullable=True),
        sa.Column('actual_cost', sa.Float(), nullable=True),
        sa.Column('depends_on', postgresql.JSONB(), server_default='[]'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create indexes for tasks
    op.create_index('ix_tasks_signal_id', 'tasks', ['signal_id'])
    op.create_index('ix_tasks_status_task_type', 'tasks', ['status', 'task_type'])
    op.create_index('ix_tasks_parent_task_id', 'tasks', ['parent_task_id'])
    op.create_index('ix_tasks_skill_id', 'tasks', ['skill_id'])
    
    # Create task_results table
    op.create_table(
        'task_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('output_data', postgresql.JSONB(), server_default='{}'),
        sa.Column('files_generated', postgresql.JSONB(), server_default='[]'),
        sa.Column('ai_calls_count', sa.Integer(), server_default='0'),
        sa.Column('total_cost', sa.Float(), server_default='0.0'),
        sa.Column('execution_time', sa.Float(), nullable=True),
        sa.Column('quality_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create human_tasks table
    op.create_table(
        'human_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('task_type', sa.String(100), nullable=False),
        sa.Column('platform', sa.String(50), nullable=True),
        sa.Column('priority', sa.String(20), server_default='normal'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('prepared_materials', postgresql.JSONB(), server_default='{}'),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('target_url', sa.String(1000), nullable=True),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by', sa.String(100), nullable=True),
        sa.Column('completion_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes for human_tasks
    op.create_index('ix_human_tasks_status_priority', 'human_tasks', ['status', 'priority'])
    op.create_index('ix_human_tasks_task_id', 'human_tasks', ['task_id'])
    op.create_index('ix_human_tasks_deadline', 'human_tasks', ['deadline'])
    
    # Create cost_records table
    op.create_table(
        'cost_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('model_tier', sa.String(20), nullable=False),
        sa.Column('input_tokens', sa.Integer(), server_default='0'),
        sa.Column('output_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost', sa.Float(), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cached', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create indexes for cost_records
    op.create_index('ix_cost_records_created_at', 'cost_records', ['created_at'])
    op.create_index('ix_cost_records_task_id', 'cost_records', ['task_id'])
    op.create_index('ix_cost_records_provider', 'cost_records', ['provider'])
    op.create_index('ix_cost_records_model_tier', 'cost_records', ['model_tier'])
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('event_type', sa.String(100), nullable=False, index=True),
        sa.Column('actor', sa.String(100), nullable=False),
        sa.Column('details', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create indexes for audit_logs
    op.create_index('ix_audit_logs_event_type_created_at', 'audit_logs', ['event_type', 'created_at'])
    op.create_index('ix_audit_logs_actor', 'audit_logs', ['actor'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    
    # Create skills table
    op.create_table(
        'skills',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('version', sa.String(20), server_default='1.0'),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('success_rate', sa.Float(), server_default='0.0'),
        sa.Column('avg_revenue', sa.Float(), server_default='0.0'),
        sa.Column('avg_ai_cost', sa.Float(), server_default='0.0'),
        sa.Column('avg_time_hours', sa.Float(), server_default='0.0'),
        sa.Column('execution_count', sa.Integer(), server_default='0'),
        sa.Column('triggers', postgresql.JSONB(), server_default='{}'),
        sa.Column('compliance', postgresql.JSONB(), server_default='{}'),
        sa.Column('workflow', postgresql.JSONB(), server_default='{}'),
        sa.Column('quality_checklist', postgresql.JSONB(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Create indexes for skills
    op.create_index('ix_skills_category', 'skills', ['category'])
    op.create_index('ix_skills_status', 'skills', ['status'])
    op.create_index('ix_skills_success_rate', 'skills', ['success_rate'])


def downgrade() -> None:
    """Downgrade database schema"""
    
    # Drop tables in reverse order
    op.drop_table('skills')
    op.drop_table('audit_logs')
    op.drop_table('cost_records')
    op.drop_table('human_tasks')
    op.drop_table('task_results')
    op.drop_table('tasks')
    op.drop_table('signals')
    
    # Drop pgvector extension (optional - might be used by other apps)
    # op.execute('DROP EXTENSION IF EXISTS vector')
