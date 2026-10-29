"""Add personal action-card baselines/revisions without changing announcements."""
from alembic import op
import sqlalchemy as sa
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('private_action_snapshots',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),nullable=False),
        sa.Column('email_id',sa.Integer(),nullable=False),sa.Column('source_index',sa.Integer(),nullable=False),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),sa.Column('source_hash',sa.String(64),nullable=False),
        sa.Column('baseline_hash',sa.String(64),nullable=False),sa.Column('parser_version',sa.String(64),nullable=False),
        sa.Column('source_text',sa.Text(),nullable=False),sa.Column('source_metadata',sa.JSON(),nullable=False),
        sa.Column('original_card',sa.JSON(),nullable=False),sa.Column('revision_count',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['user_id','email_id'],['emails.user_id','emails.id'],ondelete='CASCADE'),
        sa.UniqueConstraint('user_id','id'),sa.UniqueConstraint('user_id','email_id','source_index','source_fingerprint','baseline_hash'),
        sa.CheckConstraint('source_index >= 0',name='source_index'),sa.CheckConstraint('revision_count >= 0',name='revision_count'))
    op.create_index('ix_private_action_snapshots_user_id','private_action_snapshots',['user_id'])
    op.create_table('private_action_revisions',
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),nullable=False),
        sa.Column('snapshot_id',sa.Integer(),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('operation',sa.String(16),nullable=False),sa.Column('overrides',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['user_id','snapshot_id'],['private_action_snapshots.user_id','private_action_snapshots.id'],ondelete='CASCADE'),
        sa.UniqueConstraint('snapshot_id','revision'),sa.CheckConstraint('revision > 0',name='revision'),
        sa.CheckConstraint("operation IN ('save','reset')",name='operation'))
    op.create_index('ix_private_action_revisions_user_id','private_action_revisions',['user_id'])

def downgrade():
    op.drop_table('private_action_revisions')
    op.drop_table('private_action_snapshots')
