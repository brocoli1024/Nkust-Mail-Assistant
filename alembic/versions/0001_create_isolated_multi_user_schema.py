"""Create isolated multi-user schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('google_user_id', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=True),
    sa.Column('avatar_url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('google_user_id', name=op.f('uq_users_google_user_id'))
    )
    op.create_table('emails',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('gmail_message_id', sa.String(length=255), nullable=False),
    sa.Column('subject', sa.Text(), nullable=True),
    sa.Column('sender', sa.Text(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('html_body', sa.Text(), nullable=True),
    sa.Column('text_body', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('parser_version', sa.String(length=255), nullable=True),
    sa.Column('warnings', sa.JSON(), nullable=False),
    sa.CheckConstraint("status IN ('failed', 'processed')", name=op.f('ck_emails_status')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_emails_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_emails')),
    sa.UniqueConstraint('user_id', 'gmail_message_id', name=op.f('uq_emails_user_id_gmail_message_id')),
    sa.UniqueConstraint('user_id', 'id', name=op.f('uq_emails_user_id_id'))
    )
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_emails_received_at'), ['received_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_emails_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_emails_user_received', ['user_id', 'received_at'], unique=False)

    op.create_table('oauth_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('provider_user_id', sa.String(length=255), nullable=False),
    sa.Column('access_token_encrypted', sa.Text(), nullable=True),
    sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('scopes', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_oauth_accounts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_oauth_accounts')),
    sa.UniqueConstraint('provider', 'provider_user_id', name=op.f('uq_oauth_accounts_provider_provider_user_id')),
    sa.UniqueConstraint('user_id', 'provider', name=op.f('uq_oauth_accounts_user_id_provider'))
    )
    with op.batch_alter_table('oauth_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_oauth_accounts_user_id'), ['user_id'], unique=False)

    op.create_table('announcements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('email_id', sa.Integer(), nullable=False),
    sa.Column('source_index', sa.Integer(), nullable=False),
    sa.Column('source_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('announcement_date', sa.Date(), nullable=True),
    sa.Column('department', sa.Text(), nullable=False),
    sa.Column('source_category', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=255), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('original_text', sa.Text(), nullable=False),
    sa.Column('original_html', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('event_date', sa.Date(), nullable=True),
    sa.Column('deadline', sa.Date(), nullable=True),
    sa.Column('requires_action', sa.Boolean(), nullable=True),
    sa.Column('date_evidence', sa.JSON(), nullable=False),
    sa.Column('date_inferred', sa.Boolean(), nullable=False),
    sa.Column('keywords', sa.JSON(), nullable=False),
    sa.Column('scraped_text', sa.Text(), nullable=True),
    sa.Column('analysis_status', sa.String(length=32), nullable=False),
    sa.Column('analysis_version', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('source_index >= 0', name=op.f('ck_announcements_source_index')),
    sa.ForeignKeyConstraint(['user_id', 'email_id'], ['emails.user_id', 'emails.id'], name=op.f('fk_announcements_user_id_emails'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_announcements_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_announcements')),
    sa.UniqueConstraint('email_id', 'source_index', name=op.f('uq_announcements_email_id_source_index')),
    sa.UniqueConstraint('user_id', 'id', name=op.f('uq_announcements_user_id_id'))
    )
    with op.batch_alter_table('announcements', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_announcements_category'), ['category'], unique=False)
        batch_op.create_index(batch_op.f('ix_announcements_deadline'), ['deadline'], unique=False)
        batch_op.create_index(batch_op.f('ix_announcements_email_id'), ['email_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_announcements_event_date'), ['event_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_announcements_source_fingerprint'), ['source_fingerprint'], unique=False)
        batch_op.create_index('ix_announcements_user_category', ['user_id', 'category'], unique=False)
        batch_op.create_index('ix_announcements_user_deadline', ['user_id', 'deadline'], unique=False)
        batch_op.create_index(batch_op.f('ix_announcements_user_id'), ['user_id'], unique=False)

    op.create_table('announcement_analyses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('announcement_id', sa.Integer(), nullable=False),
    sa.Column('input_hash', sa.String(length=64), nullable=False),
    sa.Column('provider', sa.String(length=255), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('version', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('warnings', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id', 'announcement_id'], ['announcements.user_id', 'announcements.id'], name=op.f('fk_announcement_analyses_user_id_announcements'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_announcement_analyses'))
    )
    with op.batch_alter_table('announcement_analyses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_announcement_analyses_announcement_id'), ['announcement_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_announcement_analyses_user_id'), ['user_id'], unique=False)

    op.create_table('announcement_scrapes',
    sa.Column('announcement_id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('final_url', sa.Text(), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id', 'announcement_id'], ['announcements.user_id', 'announcements.id'], name=op.f('fk_announcement_scrapes_user_id_announcements'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('announcement_id', name=op.f('pk_announcement_scrapes'))
    )
    with op.batch_alter_table('announcement_scrapes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_announcement_scrapes_user_id'), ['user_id'], unique=False)



def downgrade():
    with op.batch_alter_table('announcement_scrapes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_announcement_scrapes_user_id'))

    op.drop_table('announcement_scrapes')
    with op.batch_alter_table('announcement_analyses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_announcement_analyses_user_id'))
        batch_op.drop_index(batch_op.f('ix_announcement_analyses_announcement_id'))

    op.drop_table('announcement_analyses')
    with op.batch_alter_table('announcements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_announcements_user_id'))
        batch_op.drop_index('ix_announcements_user_deadline')
        batch_op.drop_index('ix_announcements_user_category')
        batch_op.drop_index(batch_op.f('ix_announcements_source_fingerprint'))
        batch_op.drop_index(batch_op.f('ix_announcements_event_date'))
        batch_op.drop_index(batch_op.f('ix_announcements_email_id'))
        batch_op.drop_index(batch_op.f('ix_announcements_deadline'))
        batch_op.drop_index(batch_op.f('ix_announcements_category'))

    op.drop_table('announcements')
    with op.batch_alter_table('oauth_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_oauth_accounts_user_id'))

    op.drop_table('oauth_accounts')
    with op.batch_alter_table('emails', schema=None) as batch_op:
        batch_op.drop_index('ix_emails_user_received')
        batch_op.drop_index(batch_op.f('ix_emails_user_id'))
        batch_op.drop_index(batch_op.f('ix_emails_received_at'))

    op.drop_table('emails')
    op.drop_table('users')
