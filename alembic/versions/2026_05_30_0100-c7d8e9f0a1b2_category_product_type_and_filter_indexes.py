"""category product_type + filter indexes

Adds ``product_categories.product_type_id`` (each category belongs to exactly one product
type, which drives the storefront facet set) and indexes the per-type filterable attribute
columns. The column is backfilled from each category's existing products before being made
NOT NULL, so the upgrade is safe on populated databases.

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-05-30 01:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add nullable, backfill from each category's products, then enforce NOT NULL.
    op.add_column("product_categories", sa.Column("product_type_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE product_categories c
        SET product_type_id = sub.product_type_id
        FROM (
            SELECT product_category_id, product_type_id
            FROM (
                SELECT product_category_id, product_type_id,
                       row_number() OVER (
                           PARTITION BY product_category_id ORDER BY count(*) DESC
                       ) AS rn
                FROM products
                GROUP BY product_category_id, product_type_id
            ) ranked
            WHERE rn = 1
        ) sub
        WHERE c.id = sub.product_category_id
        """
    )
    op.alter_column("product_categories", "product_type_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_product_categories_product_type_id_product_types"),
        "product_categories",
        "product_types",
        ["product_type_id"],
        ["id"],
    )
    op.create_index(
        "idx_product_categories_product_type_id",
        "product_categories",
        ["product_type_id"],
        unique=False,
    )

    # Index the per-type filterable attribute columns.
    op.create_index("idx_product_equipment_equipment_type", "product_equipment", ["equipment_type"])
    op.create_index("idx_product_equipment_material", "product_equipment", ["material"])
    op.create_index("idx_product_equipment_power_watts", "product_equipment", ["power_watts"])
    op.create_index(
        "idx_product_accessories_accessory_type", "product_accessories", ["accessory_type"]
    )
    op.create_index("idx_product_accessories_material", "product_accessories", ["material"])
    op.create_index(
        "idx_product_consumables_consumable_type", "product_consumables", ["consumable_type"]
    )
    op.create_index("idx_product_consumables_material", "product_consumables", ["material"])
    op.create_index(
        "idx_product_consumables_quantity_per_pack", "product_consumables", ["quantity_per_pack"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_product_consumables_quantity_per_pack", table_name="product_consumables")
    op.drop_index("idx_product_consumables_material", table_name="product_consumables")
    op.drop_index("idx_product_consumables_consumable_type", table_name="product_consumables")
    op.drop_index("idx_product_accessories_material", table_name="product_accessories")
    op.drop_index("idx_product_accessories_accessory_type", table_name="product_accessories")
    op.drop_index("idx_product_equipment_power_watts", table_name="product_equipment")
    op.drop_index("idx_product_equipment_material", table_name="product_equipment")
    op.drop_index("idx_product_equipment_equipment_type", table_name="product_equipment")

    op.drop_index("idx_product_categories_product_type_id", table_name="product_categories")
    op.drop_constraint(
        op.f("fk_product_categories_product_type_id_product_types"),
        "product_categories",
        type_="foreignkey",
    )
    op.drop_column("product_categories", "product_type_id")
