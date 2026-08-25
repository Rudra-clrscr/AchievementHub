"""split tier-1 verification from tier-2 approval on achievements

Both tiers used to write `verified_by`/`verified_at`, so an admin approval
overwrote the faculty coordinator's signature. That made it impossible to show
a verifier what they had personally reviewed: for a coordinator, the records
that completed the pipeline were exactly the ones whose signature had been
replaced.

`approved_by`/`approved_at` now hold the tier-2 decision and `verified_by`
keeps the tier-1 one.

Backfill note: for rows already in `approved`, the last actor *was* an admin,
so `verified_by` is copied into `approved_by`. The original tier-1 verifier for
those rows is genuinely unrecoverable -- it was overwritten before this column
existed -- so their `verified_by` is left as-is rather than invented. Rows in
`rejected` are deliberately left alone: either tier can reject, and there is no
way to tell which one did from the data.

Revision ID: e5c71b9a3d80
Revises: b7d1a2e3f4c5
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5c71b9a3d80"
down_revision: Union[str, None] = "b7d1a2e3f4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("achievements", sa.Column("approved_by", sa.Integer(), nullable=True))
    op.add_column(
        "achievements", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_achievements_approved_by_employees",
        "achievements",
        "employees",
        ["approved_by"],
        ["emp_id"],
    )
    op.execute(
        """
        UPDATE achievements
        SET approved_by = verified_by,
            approved_at = verified_at
        WHERE status = 'approved' AND verified_by IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_achievements_approved_by_employees", "achievements", type_="foreignkey")
    op.drop_column("achievements", "approved_at")
    op.drop_column("achievements", "approved_by")
