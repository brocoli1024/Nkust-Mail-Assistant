"""Add explicit private todos. Never migrates the legacy local application."""
from alembic import op
import sqlalchemy as sa
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('private_todos',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),nullable=False),sa.Column('email_id',sa.Integer(),nullable=False),
        sa.Column('source_ref',sa.String(512),nullable=False),sa.Column('source_index',sa.Integer(),nullable=False),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),sa.Column('card',sa.JSON(),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),sa.Column('snoozed_until',sa.DateTime(timezone=True)),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['user_id','email_id'],['emails.user_id','emails.id'],ondelete='CASCADE'),
        sa.UniqueConstraint('user_id','source_ref'),sa.CheckConstraint('revision > 0',name='revision'),
        sa.CheckConstraint("status IN ('active','done','snoozed','removed')",name='status'),
        sa.CheckConstraint("(status = 'snoozed' AND snoozed_until IS NOT NULL) OR (status != 'snoozed' AND snoozed_until IS NULL)",name='snooze'))
    op.create_index('ix_private_todos_user_id','private_todos',['user_id'])

def downgrade():
    op.drop_table('private_todos')
