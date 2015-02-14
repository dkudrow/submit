"""Add maximum group members setting to project.

Revision ID: 34ac45196731
Revises: 385c579612dd
Create Date: 2013-09-18 14:39:22.252591

"""

# revision identifiers, used by Alembic.
revision = '34ac45196731'
down_revision = '385c579612dd'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('project', sa.Column('group_max', sa.Integer(), server_default=u'1', nullable=False))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('project', 'group_max')
    ### end Alembic commands ###