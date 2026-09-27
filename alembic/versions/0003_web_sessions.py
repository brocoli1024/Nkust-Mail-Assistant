"""Revocable server-side sessions, storing only hashed session IDs."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('web_sessions',
                    sa.Column('id_hash', sa.String(64), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.PrimaryKeyConstraint('id_hash', name='pk_web_sessions'),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_web_sessions_user_id_users'))
    op.create_index('ix_web_sessions_user_id', 'web_sessions', ['user_id'])
    op.create_index('ix_web_sessions_expires_at', 'web_sessions', ['expires_at'])


def downgrade():
    op.drop_index('ix_web_sessions_expires_at', table_name='web_sessions')
    op.drop_index('ix_web_sessions_user_id', table_name='web_sessions')
    op.drop_table('web_sessions')
