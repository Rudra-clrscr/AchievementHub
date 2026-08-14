"""add employee ownership columns to certificates table

Revision ID: c4e289f01234
Revises: b3f1d82e4a90
Create Date: 2026-08-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e289f01234'
down_revision: Union[str, None] = 'b3f1d82e4a90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('certificates', sa.Column('owner_type', sa.Enum('student', 'employee', name='ownertype'), server_default='student', nullable=False))
    op.add_column('certificates', sa.Column('employee_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_certificates_employee_id', 'certificates', 'employees', ['employee_id'], ['emp_id'])
    op.alter_column('certificates', 'student_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column('certificates', 'student_id', existing_type=sa.Integer(), nullable=False)
    op.drop_constraint('fk_certificates_employee_id', 'certificates', type_='foreignkey')
    op.drop_column('certificates', 'employee_id')
    op.drop_column('certificates', 'owner_type')
