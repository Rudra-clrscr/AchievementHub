"""add is_featured to certificates, publications, patents, internships, event participations

Revision ID: b3f1a9d2c5e7
Revises: 7826a8516734
Create Date: 2026-08-07 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1a9d2c5e7'
down_revision: Union[str, None] = '7826a8516734'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('certificates', 'research_publications', 'patents', 'internships', 'event_participations')


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column('is_featured', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, 'is_featured')
