"""One-use server-side OAuth transactions (no authenticated sessions)."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('oauth_attempts',
                    sa.Column('state_hash', sa.String(64), nullable=False),
                    sa.Column('browser_hash', sa.String(64), nullable=False),
                    sa.Column('context_encrypted', sa.Text(), nullable=False),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.PrimaryKeyConstraint('state_hash', name='pk_oauth_attempts'))
    op.create_index('ix_oauth_attempts_expires_at', 'oauth_attempts', ['expires_at'])


def downgrade():
    op.drop_index('ix_oauth_attempts_expires_at', table_name='oauth_attempts')
    op.drop_table('oauth_attempts')
