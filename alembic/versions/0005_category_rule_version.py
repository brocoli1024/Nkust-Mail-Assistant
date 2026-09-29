"""Track which deterministic category rules have examined an announcement."""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('announcements') as batch_op:
        batch_op.add_column(sa.Column('category_rule_version', sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table('announcements') as batch_op:
        batch_op.drop_column('category_rule_version')
