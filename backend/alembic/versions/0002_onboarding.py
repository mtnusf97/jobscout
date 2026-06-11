"""onboarding: documents, master_profiles, interview_questions

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="uploaded"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("extracted_json", sa.JSON(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "master_profiles",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="build"),
        sa.Column("body_json", sa.JSON(), nullable=False),
        sa.Column("built_from", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("interview_questions")
    op.drop_table("master_profiles")
    op.drop_table("documents")
