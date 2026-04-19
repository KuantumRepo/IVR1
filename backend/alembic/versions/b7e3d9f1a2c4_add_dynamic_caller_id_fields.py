"""add_dynamic_caller_id_fields

Revision ID: b7e3d9f1a2c4
Revises: a2515f1dc80c
Create Date: 2026-04-19 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e3d9f1a2c4'
down_revision: Union[str, Sequence[str], None] = 'a2515f1dc80c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dynamic caller ID columns to campaigns."""
    op.add_column('campaigns', sa.Column(
        'enable_dynamic_caller_id', sa.Boolean(),
        nullable=False, server_default=sa.text('false')
    ))
    op.add_column('campaigns', sa.Column(
        'dynamic_caller_id_ratio', sa.Integer(),
        nullable=False, server_default=sa.text('100')
    ))


def downgrade() -> None:
    """Remove dynamic caller ID columns."""
    op.drop_column('campaigns', 'dynamic_caller_id_ratio')
    op.drop_column('campaigns', 'enable_dynamic_caller_id')
