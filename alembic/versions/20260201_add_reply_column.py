"""add comment reply options

Revision ID: add_reply_options
Revises: 59008a36739b
Create Date: 2026-02-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_reply_options'
down_revision: Union[str, None] = '59008a36739b' # This points to your previous migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the missing column
    op.add_column('automations', sa.Column('comment_reply_options', sa.JSON(), nullable=True, server_default='[]'))


def downgrade() -> None:
    # Remove it if we rollback
    op.drop_column('automations', 'comment_reply_options')