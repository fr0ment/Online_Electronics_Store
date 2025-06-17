"""add average_rating and order_items

Revision ID: aa03c32881d9
Revises: 1
Create Date: 2025-06-17 04:53:03.728458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa03c32881d9'
down_revision: Union[str, None] = '1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('average_rating', sa.Float(), nullable=True))
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, default=1),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade() -> None:
    op.drop_column('products', 'average_rating')
    op.drop_table('order_items')
