"""rename categories to product_categories

Renames the ``categories`` table to ``product_categories`` and the
``products.category_id`` FK column to ``product_category_id``, keeping every
constraint/index name aligned with the metadata NAMING_CONVENTION. Pure rename:
no data is moved or dropped, fully reversible.

Revision ID: b1c2d3e4f5a6
Revises: 2848920356cc
Create Date: 2026-05-30 00:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "2848920356cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Table + its own constraints/index.
    op.rename_table("categories", "product_categories")
    op.execute(
        "ALTER TABLE product_categories RENAME CONSTRAINT pk_categories TO pk_product_categories"
    )
    op.execute(
        "ALTER TABLE product_categories RENAME CONSTRAINT uq_categories_name "
        "TO uq_product_categories_name"
    )
    op.execute("ALTER INDEX idx_categories_is_active RENAME TO idx_product_categories_is_active")

    # FK column on products + its index and FK constraint.
    op.alter_column("products", "category_id", new_column_name="product_category_id")
    op.execute("ALTER INDEX idx_products_category_id RENAME TO idx_products_product_category_id")
    op.execute(
        "ALTER TABLE products RENAME CONSTRAINT fk_products_category_id_categories "
        "TO fk_products_product_category_id_product_categories"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER TABLE products RENAME CONSTRAINT fk_products_product_category_id_product_categories "
        "TO fk_products_category_id_categories"
    )
    op.execute("ALTER INDEX idx_products_product_category_id RENAME TO idx_products_category_id")
    op.alter_column("products", "product_category_id", new_column_name="category_id")

    op.execute("ALTER INDEX idx_product_categories_is_active RENAME TO idx_categories_is_active")
    op.execute(
        "ALTER TABLE product_categories RENAME CONSTRAINT uq_product_categories_name "
        "TO uq_categories_name"
    )
    op.execute(
        "ALTER TABLE product_categories RENAME CONSTRAINT pk_product_categories TO pk_categories"
    )
    op.rename_table("product_categories", "categories")
