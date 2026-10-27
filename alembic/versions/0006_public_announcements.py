"""Add independent public source records, maintenance runs and source cursor."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('public_announcements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_key', sa.String(64), nullable=False),
        sa.Column('canonical_url', sa.Text(), nullable=False),
        sa.Column('external_id', sa.Text()),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('category', sa.String(255)),
        sa.Column('category_rule_version', sa.String(64)),
        sa.Column('student_relevance', sa.String(32), nullable=False),
        sa.Column('student_reason', sa.JSON(), nullable=False),
        sa.Column('student_rule_version', sa.String(64)),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('source_key', 'canonical_url'),
        sa.CheckConstraint("student_relevance IN ('relevant','not_student','unknown')", name='student_relevance'))
    for field in ('published_at', 'category', 'student_relevance'):
        op.create_index('ix_public_announcements_' + field, 'public_announcements', [field])
    op.create_table('public_sync_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_key', sa.String(64), nullable=False),
        sa.Column('mode', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('added', sa.Integer(), nullable=False),
        sa.Column('updated', sa.Integer(), nullable=False),
        sa.Column('unchanged', sa.Integer(), nullable=False),
        sa.Column('failed', sa.Integer(), nullable=False),
        sa.Column('error_code', sa.String(64)),
        sa.CheckConstraint("mode IN ('recent','history','reclassify')", name='mode'),
        sa.CheckConstraint("status IN ('running','success','partial','failed')", name='status'))
    op.create_table('public_source_states',
        sa.Column('source_key', sa.String(64), primary_key=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True)),
        sa.Column('oldest_seen_at', sa.DateTime(timezone=True)),
        sa.Column('next_history_page', sa.Integer(), nullable=False),
        sa.Column('history_status', sa.String(32), nullable=False),
        sa.Column('history_completed_at', sa.DateTime(timezone=True)),
        sa.Column('lease_owner', sa.String(64)),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("history_status IN ('not_started','incomplete','complete')", name='history_status'),
        sa.CheckConstraint('next_history_page >= 1', name='next_history_page'))


def downgrade():
    op.drop_table('public_source_states')
    op.drop_table('public_sync_runs')
    op.drop_table('public_announcements')
