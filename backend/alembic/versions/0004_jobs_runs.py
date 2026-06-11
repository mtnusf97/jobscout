"""jobs and runs tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources_json", sa.JSON(), nullable=False),
        sa.Column("urls_json", sa.JSON(), nullable=False),
        sa.Column("canonical_url", sa.String(length=800), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("remote_type", sa.String(length=32), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=8), nullable=True),
        sa.Column("salary_is_estimate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("jd_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="discovered"),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_jobs_dedupe_key", "jobs", ["dedupe_key"])
    op.create_index("ix_jobs_profile_status", "jobs", ["profile_id", "status"])
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "profile_id",
            sa.String(length=32),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="discovery"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats_json", sa.JSON(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_index("ix_jobs_profile_status", table_name="jobs")
    op.drop_index("ix_jobs_dedupe_key", table_name="jobs")
    op.drop_table("jobs")
