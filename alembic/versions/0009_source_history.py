"""Retain isolated source versions without rewriting announcements."""
from alembic import op
import sqlalchemy as sa
revision='0009'
down_revision='0008'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('public_source_versions',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('source_key',sa.String(80),nullable=False),sa.Column('canonical_url',sa.String(4096),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),
        sa.Column('captured_at',sa.DateTime(timezone=True),nullable=False),sa.Column('baseline',sa.Boolean(),nullable=False))
    op.create_index('ix_public_source_versions_source_key','public_source_versions',['source_key'])
    op.create_table('private_source_versions',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),nullable=False),sa.Column('email_id',sa.Integer(),nullable=False),
        sa.Column('source_index',sa.Integer(),nullable=False),sa.Column('source_fingerprint',sa.String(64),nullable=False),
        sa.Column('canonical_url',sa.String(4096)),sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('snapshot',sa.JSON(),nullable=False),sa.Column('captured_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('baseline',sa.Boolean(),nullable=False),
        sa.ForeignKeyConstraint(['user_id','email_id'],['emails.user_id','emails.id'],ondelete='CASCADE'),
        sa.CheckConstraint('source_index >= 0',name='source_index'))
    op.create_index('ix_private_source_versions_user_id','private_source_versions',['user_id'])

def downgrade():
    op.drop_table('private_source_versions')
    op.drop_table('public_source_versions')
