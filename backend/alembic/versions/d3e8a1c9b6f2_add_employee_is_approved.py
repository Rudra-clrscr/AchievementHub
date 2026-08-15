"""add_employee_is_approved

Revision ID: d3e8a1c9b6f2
Revises: c1a9f6b7e2d4
Create Date: 2026-08-15 00:00:00.000000

Adds employees.is_approved, defaulting true so every existing account
(seeded or otherwise) stays usable. Self-registered faculty/HOD accounts
explicitly set it false at signup and need an admin to flip it before
they can log in.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e8a1c9b6f2'
down_revision: Union[str, None] = 'c1a9f6b7e2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'employees',
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    pass
