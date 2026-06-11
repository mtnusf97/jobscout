"""initial schema: profiles, credentials

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="instance"),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value_enc", sa.LargeBinary(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "profile_id", "name", name="uq_credentials_scope_profile_name"),
    )


def downgrade() -> None:
    op.drop_table("credentials")
    op.drop_table("profiles")
