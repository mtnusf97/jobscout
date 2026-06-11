"""telegram bots + packet delivery markers

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_bots",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bot_token_enc", sa.LargeBinary(), nullable=False),
        sa.Column("bot_username", sa.String(length=64), nullable=False),
        sa.Column("link_code", sa.String(length=16), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", name="uq_telegram_bots_profile"),
    )
    op.add_column("packets", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("packets", sa.Column("telegram_msg_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("packets", "telegram_msg_id")
    op.drop_column("packets", "delivered_at")
    op.drop_table("telegram_bots")
