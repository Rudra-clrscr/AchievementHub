"""multi_role_employees

Revision ID: c1a9f6b7e2d4
Revises: 8909d0f33a81
Create Date: 2026-08-13 00:00:00.000000

Replaces the single Employee.role column with a many-to-many
employee_roles table (an employee can now hold more than one role), and
folds the old admin_hod/admin_clerk split into a single "admin" role plus
a separate "hod" role. HOD oversight of faculty becomes an explicit
assignment (employees.hod_id), mirroring students.coordinator_id, instead
of the old department-based scoping.

Backfill mapping from the old role column:
  faculty_coordinator -> faculty
  admin_clerk         -> admin
  admin_hod           -> admin AND hod (old admin_hod could verify both
                         students and faculty at the department level;
                         granting both new roles preserves that reach)
  principal           -> principal (unused, unchanged)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1a9f6b7e2d4'
down_revision: Union[str, None] = '8909d0f33a81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    new_role_enum = postgresql.ENUM('faculty', 'hod', 'admin', 'principal', name='employeerole_new')
    new_role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'employee_roles',
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.emp_id'), primary_key=True),
        sa.Column(
            'role',
            postgresql.ENUM('faculty', 'hod', 'admin', 'principal', name='employeerole_new', create_type=False),
            primary_key=True,
        ),
    )

    op.execute(
        """
        INSERT INTO employee_roles (employee_id, role)
        SELECT emp_id, 'faculty'::employeerole_new FROM employees WHERE role::text = 'faculty_coordinator'
        UNION ALL
        SELECT emp_id, 'admin'::employeerole_new FROM employees WHERE role::text IN ('admin_clerk', 'admin_hod')
        UNION ALL
        SELECT emp_id, 'hod'::employeerole_new FROM employees WHERE role::text = 'admin_hod'
        UNION ALL
        SELECT emp_id, 'principal'::employeerole_new FROM employees WHERE role::text = 'principal'
        """
    )

    op.add_column('employees', sa.Column('hod_id', sa.Integer(), sa.ForeignKey('employees.emp_id'), nullable=True))

    op.drop_column('employees', 'role')
    op.execute('DROP TYPE employeerole')
    op.execute('ALTER TYPE employeerole_new RENAME TO employeerole')


def downgrade() -> None:
    pass
