"""Add unified Achievement table with data migration

Revision ID: ffc0eafda47c
Revises: 3aaaefd81b0a
Create Date: 2026-08-09 13:43:50.156494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json

# revision identifiers, used by Alembic.
revision: str = 'ffc0eafda47c'
down_revision: Union[str, None] = '3aaaefd81b0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the new achievements table
    achievements_table = op.create_table('achievements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('sub_category', sa.String(length=100), nullable=True),
    sa.Column('metadata_fields', sa.JSON(), nullable=True),
    sa.Column('owner_type', postgresql.ENUM('student', 'employee', name='ownertype', create_type=False), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=True),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('file_url', sa.String(length=500), nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='certificatestatus', create_type=False), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('verified_by', sa.Integer(), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_featured', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.emp_id'], ),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], ),
    sa.ForeignKeyConstraint(['verified_by'], ['employees.emp_id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # 2. Data Migration: Copy from old tables to new table
    conn = op.get_bind()
    
    # 2a. Certificates
    certs = conn.execute(sa.text("SELECT * FROM certificates")).mappings()
    for row in certs:
        meta = {}
        if row.get('issuer'): meta['issuer'] = row['issuer']
        
        conn.execute(
            sa.text("""
            INSERT INTO achievements (title, category, sub_category, metadata_fields, owner_type, student_id, employee_id, file_url, status, submitted_at, verified_by, verified_at, is_featured, thumbnail_url)
            VALUES (:title, :category, :sub_category, :metadata_fields, 'student', :student_id, NULL, :file_url, :status, :submitted_at, :verified_by, :verified_at, :is_featured, :thumbnail_url)
            """),
            {
                "title": row['title'],
                "category": "Certifications",
                "sub_category": row['category'].value if hasattr(row['category'], 'value') else row['category'],
                "metadata_fields": json.dumps(meta),
                "student_id": row['student_id'],
                "file_url": row['file_url'],
                "status": row['status'].value if hasattr(row['status'], 'value') else row['status'],
                "submitted_at": row['submitted_at'],
                "verified_by": row['verified_by'],
                "verified_at": row['verified_at'],
                "is_featured": row.get('is_featured', False),
                "thumbnail_url": row.get('thumbnail_url', None)
            }
        )

    # 2b. Research Publications
    pubs = conn.execute(sa.text("SELECT * FROM research_publications")).mappings()
    for row in pubs:
        meta = {}
        if row.get('venue'): meta['venue'] = row['venue']
        if row.get('publication_date'): meta['publication_date'] = str(row['publication_date'])
        
        conn.execute(
            sa.text("""
            INSERT INTO achievements (title, category, metadata_fields, owner_type, student_id, employee_id, file_url, status, submitted_at, verified_by, verified_at, is_featured, thumbnail_url)
            VALUES (:title, :category, :metadata_fields, :owner_type, :student_id, :employee_id, :file_url, :status, :submitted_at, :verified_by, :verified_at, :is_featured, :thumbnail_url)
            """),
            {
                "title": row['title'],
                "category": "Research & Publications" if row['owner_type'] == 'student' else "Research Publications",
                "metadata_fields": json.dumps(meta),
                "owner_type": row['owner_type'].value if hasattr(row['owner_type'], 'value') else row['owner_type'],
                "student_id": row['student_id'],
                "employee_id": row['employee_id'],
                "file_url": row['file_url'],
                "status": row['status'].value if hasattr(row['status'], 'value') else row['status'],
                "submitted_at": row['submitted_at'],
                "verified_by": row['verified_by'],
                "verified_at": row['verified_at'],
                "is_featured": row.get('is_featured', False),
                "thumbnail_url": row.get('thumbnail_url', None)
            }
        )

    # 2c. Patents
    patents = conn.execute(sa.text("SELECT * FROM patents")).mappings()
    for row in patents:
        meta = {}
        if row.get('patent_number'): meta['patent_number'] = row['patent_number']
        if row.get('filing_date'): meta['filing_date'] = str(row['filing_date'])
        
        conn.execute(
            sa.text("""
            INSERT INTO achievements (title, category, metadata_fields, owner_type, student_id, employee_id, file_url, status, submitted_at, verified_by, verified_at, is_featured, thumbnail_url)
            VALUES (:title, :category, :metadata_fields, :owner_type, :student_id, :employee_id, :file_url, :status, :submitted_at, :verified_by, :verified_at, :is_featured, :thumbnail_url)
            """),
            {
                "title": row['title'],
                "category": "Intellectual Property",
                "metadata_fields": json.dumps(meta),
                "owner_type": row['owner_type'].value if hasattr(row['owner_type'], 'value') else row['owner_type'],
                "student_id": row['student_id'],
                "employee_id": row['employee_id'],
                "file_url": row['file_url'],
                "status": row['status'].value if hasattr(row['status'], 'value') else row['status'],
                "submitted_at": row['submitted_at'],
                "verified_by": row['verified_by'],
                "verified_at": row['verified_at'],
                "is_featured": row.get('is_featured', False),
                "thumbnail_url": row.get('thumbnail_url', None)
            }
        )
        
    # 2d. Internships
    internships = conn.execute(sa.text("SELECT * FROM internships")).mappings()
    for row in internships:
        meta = {}
        if row.get('role_title'): meta['role_title'] = row['role_title']
        if row.get('organization'): meta['organization'] = row['organization']
        if row.get('start_date'): meta['start_date'] = str(row['start_date'])
        if row.get('end_date'): meta['end_date'] = str(row['end_date'])
        
        conn.execute(
            sa.text("""
            INSERT INTO achievements (title, category, metadata_fields, owner_type, student_id, employee_id, file_url, status, submitted_at, verified_by, verified_at, is_featured, thumbnail_url)
            VALUES (:title, :category, :metadata_fields, :owner_type, :student_id, :employee_id, :file_url, :status, :submitted_at, :verified_by, :verified_at, :is_featured, :thumbnail_url)
            """),
            {
                "title": f"Internship at {row['organization']}",
                "category": "Internship & Industrial Training",
                "metadata_fields": json.dumps(meta),
                "owner_type": row['owner_type'].value if hasattr(row['owner_type'], 'value') else row['owner_type'],
                "student_id": row['student_id'],
                "employee_id": row['employee_id'],
                "file_url": row['file_url'],
                "status": row['status'].value if hasattr(row['status'], 'value') else row['status'],
                "submitted_at": row['submitted_at'],
                "verified_by": row['verified_by'],
                "verified_at": row['verified_at'],
                "is_featured": row.get('is_featured', False),
                "thumbnail_url": row.get('thumbnail_url', None)
            }
        )

    # 2e. Event Participations
    events = conn.execute(sa.text("SELECT * FROM event_participations")).mappings()
    for row in events:
        meta = {}
        if row.get('event_name'): meta['event_name'] = row['event_name']
        if row.get('event_date'): meta['event_date'] = str(row['event_date'])
        if row.get('participation_role'): meta['participation_role'] = row['participation_role']
        
        conn.execute(
            sa.text("""
            INSERT INTO achievements (title, category, metadata_fields, owner_type, student_id, employee_id, file_url, status, submitted_at, verified_by, verified_at, is_featured, thumbnail_url)
            VALUES (:title, :category, :metadata_fields, :owner_type, :student_id, :employee_id, :file_url, :status, :submitted_at, :verified_by, :verified_at, :is_featured, :thumbnail_url)
            """),
            {
                "title": row['event_name'],
                "category": "Event Participation" if row['owner_type'] == 'student' else "Event Organization",
                "metadata_fields": json.dumps(meta),
                "owner_type": row['owner_type'].value if hasattr(row['owner_type'], 'value') else row['owner_type'],
                "student_id": row['student_id'],
                "employee_id": row['employee_id'],
                "file_url": row['file_url'],
                "status": row['status'].value if hasattr(row['status'], 'value') else row['status'],
                "submitted_at": row['submitted_at'],
                "verified_by": row['verified_by'],
                "verified_at": row['verified_at'],
                "is_featured": row.get('is_featured', False),
                "thumbnail_url": row.get('thumbnail_url', None)
            }
        )

    # 3. Drop old tables
    op.drop_table('event_participations')
    op.drop_table('patents')
    op.drop_table('research_publications')
    op.drop_table('internships')
    op.drop_table('certificates')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('certificates',
    sa.Column('cert_id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('title', sa.VARCHAR(length=300), autoincrement=False, nullable=False),
    sa.Column('issuer', sa.VARCHAR(length=200), autoincrement=False, nullable=True),
    sa.Column('category', postgresql.ENUM('FDP', 'external', 'NPTEL', 'IEEE', name='certificatecategory'), autoincrement=False, nullable=False),
    sa.Column('owner_type', postgresql.ENUM('student', 'employee', name='ownertype'), autoincrement=False, nullable=False),
    sa.Column('student_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('employee_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('file_url', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='certificatestatus'), autoincrement=False, nullable=False),
    sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('verified_by', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_featured', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('thumbnail_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.emp_id'], name='certificates_employee_id_fkey'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name='certificates_student_id_fkey'),
    sa.ForeignKeyConstraint(['verified_by'], ['employees.emp_id'], name='certificates_verified_by_fkey'),
    sa.PrimaryKeyConstraint('cert_id', name='certificates_pkey')
    )
    op.create_table('internships',
    sa.Column('internship_id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('organization', sa.VARCHAR(length=200), autoincrement=False, nullable=False),
    sa.Column('role_title', sa.VARCHAR(length=200), autoincrement=False, nullable=True),
    sa.Column('start_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('end_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('owner_type', postgresql.ENUM('student', 'employee', name='ownertype'), autoincrement=False, nullable=False),
    sa.Column('student_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('employee_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('file_url', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='certificatestatus'), autoincrement=False, nullable=False),
    sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('verified_by', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_featured', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('thumbnail_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.emp_id'], name='internships_employee_id_fkey'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name='internships_student_id_fkey'),
    sa.ForeignKeyConstraint(['verified_by'], ['employees.emp_id'], name='internships_verified_by_fkey'),
    sa.PrimaryKeyConstraint('internship_id', name='internships_pkey')
    )
    op.create_table('research_publications',
    sa.Column('pub_id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('title', sa.VARCHAR(length=300), autoincrement=False, nullable=False),
    sa.Column('venue', sa.VARCHAR(length=300), autoincrement=False, nullable=True),
    sa.Column('publication_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('owner_type', postgresql.ENUM('student', 'employee', name='ownertype'), autoincrement=False, nullable=False),
    sa.Column('student_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('employee_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('file_url', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='certificatestatus'), autoincrement=False, nullable=False),
    sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('verified_by', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_featured', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('thumbnail_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.emp_id'], name='research_publications_employee_id_fkey'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name='research_publications_student_id_fkey'),
    sa.ForeignKeyConstraint(['verified_by'], ['employees.emp_id'], name='research_publications_verified_by_fkey'),
    sa.PrimaryKeyConstraint('pub_id', name='research_publications_pkey')
    )
    op.create_table('patents',
    sa.Column('patent_id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('title', sa.VARCHAR(length=300), autoincrement=False, nullable=False),
    sa.Column('patent_number', sa.VARCHAR(length=120), autoincrement=False, nullable=True),
    sa.Column('filing_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('owner_type', postgresql.ENUM('student', 'employee', name='ownertype'), autoincrement=False, nullable=False),
    sa.Column('student_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('employee_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('file_url', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='certificatestatus'), autoincrement=False, nullable=False),
    sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('verified_by', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_featured', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('thumbnail_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.emp_id'], name='patents_employee_id_fkey'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name='patents_student_id_fkey'),
    sa.ForeignKeyConstraint(['verified_by'], ['employees.emp_id'], name='patents_verified_by_fkey'),
    sa.PrimaryKeyConstraint('patent_id', name='patents_pkey')
    )
    op.create_table('event_participations',
    sa.Column('event_id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('event_name', sa.VARCHAR(length=300), autoincrement=False, nullable=False),
    sa.Column('event_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('participation_role', postgresql.ENUM('participant', 'organizer', name='participationrole'), autoincrement=False, nullable=False),
    sa.Column('owner_type', postgresql.ENUM('student', 'employee', name='ownertype'), autoincrement=False, nullable=False),
    sa.Column('student_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('employee_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('file_url', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='certificatestatus'), autoincrement=False, nullable=False),
    sa.Column('submitted_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('verified_by', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_featured', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('thumbnail_url', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.emp_id'], name='event_participations_employee_id_fkey'),
    sa.ForeignKeyConstraint(['student_id'], ['students.student_id'], name='event_participations_student_id_fkey'),
    sa.ForeignKeyConstraint(['verified_by'], ['employees.emp_id'], name='event_participations_verified_by_fkey'),
    sa.PrimaryKeyConstraint('event_id', name='event_participations_pkey')
    )
    op.drop_table('achievements')
    # ### end Alembic commands ###
