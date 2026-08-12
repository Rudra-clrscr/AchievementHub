"""add_verified_status

Revision ID: 8909d0f33a81
Revises: 6a30aab657aa
Create Date: 2026-08-12 19:17:13.050652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8909d0f33a81'
down_revision: Union[str, None] = '6a30aab657aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE certificatestatus ADD VALUE IF NOT EXISTS 'verified'")


def downgrade() -> None:
    pass
