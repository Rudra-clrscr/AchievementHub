"""add staged certificate status values

Revision ID: b3f1d82e4a90
Revises: 7a6c82869f97
Create Date: 2026-08-09 12:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1d82e4a90'
down_revision: Union[str, None] = '7a6c82869f97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in PostgreSQL.
    # We commit the transaction context, execute raw ALTER TYPE statements on the connection,
    # and Alembic will continue.
    conn = op.get_bind()
    conn.execute(sa.text("COMMIT"))
    for val in ["pending_hod", "pending_admin", "revision_required"]:
        conn.execute(sa.text(f"ALTER TYPE certificatestatus ADD VALUE IF NOT EXISTS '{val}'"))
        conn.execute(sa.text(f"ALTER TYPE absolutecertificatestatus ADD VALUE IF NOT EXISTS '{val}'"))


def downgrade() -> None:
    pass

