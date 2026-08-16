"""add sections table and hierarchical academic structure with auto migration

Revision ID: b7d1a2e3f4c5
Revises: d3e8a1c9b6f2
Create Date: 2026-08-16 21:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1a2e3f4c5'
down_revision: Union[str, None] = 'd3e8a1c9b6f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create sections table
    op.create_table(
        'sections',
        sa.Column('section_id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('section_name', sa.String(length=50), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.dept_id'), nullable=False),
        sa.Column('coordinator_id', sa.Integer(), sa.ForeignKey('employees.emp_id'), nullable=True),
        sa.PrimaryKeyConstraint('section_id')
    )

    # 2. Add section_id and year columns to students table
    op.add_column('students', sa.Column('section_id', sa.Integer(), sa.ForeignKey('sections.section_id'), nullable=True))
    op.add_column('students', sa.Column('year', sa.Integer(), nullable=True))

    # 3. Data Auto-Migration Step:
    # For every existing department, create default Year 1 Section 'Sec 1' if not present
    op.execute("""
        INSERT INTO sections (section_name, year, department_id)
        SELECT 'Sec 1', 1, dept_id FROM departments
        ON CONFLICT DO NOTHING;
    """)

    # Map existing students who don't have a section to their department's default section and set year=1
    op.execute("""
        UPDATE students s
        SET section_id = sec.section_id,
            year = COALESCE(s.year, 1)
        FROM sections sec
        WHERE s.department_id = sec.department_id
          AND sec.year = 1
          AND s.section_id IS NULL;
    """)


def downgrade() -> None:
    op.drop_column('students', 'year')
    op.drop_column('students', 'section_id')
    op.drop_table('sections')
