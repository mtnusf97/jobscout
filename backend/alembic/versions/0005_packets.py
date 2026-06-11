"""packets table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "packets",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(length=32),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ready"),
        sa.Column("tailor_json", sa.JSON(), nullable=False),
        sa.Column("audit_json", sa.JSON(), nullable=True),
        sa.Column("resume_pdf", sa.String(length=500), nullable=True),
        sa.Column("letter_pdf", sa.String(length=500), nullable=True),
        sa.Column("retailor_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_packets_job", "packets", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_packets_job", table_name="packets")
    op.drop_table("packets")
