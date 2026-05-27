"""Idempotent dev/test seed, run by the Docker `init` service after migrations.

Loads a baseline dataset using the ORM models: known dev users (OAuth accounts +
preferences) and a representative catalog (categories, product types, products with
their type-specific attributes, and compatibility links). Dev/test only — refuses to
run in stage/prod. Re-running is a no-op (idempotent on natural keys).

Entry point: ``python -m scripts.seed_dev``.
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.database import async_session_maker
from src.auth.enums import Provider
from src.auth.models import OAuthAccount
from src.catalog.enums import (
    AccessoryType,
    ConsumableType,
    EquipmentType,
    ProcessingMethod,
    ProductTypeName,
    RoastLevel,
)
from src.catalog.models import (
    Category,
    Product,
    ProductAccessories,
    ProductCoffee,
    ProductCompatibility,
    ProductConsumables,
    ProductEquipment,
    ProductType,
)
from src.users.models import User, UserPreferences

logger = logging.getLogger("scripts.seed_dev")

_ALLOWED_ENVS = {"dev", "test"}


# --------------------------------------------------------------------------- users


@dataclass(frozen=True, slots=True)
class SeedUser:
    """A deterministic seed identity. Login matches on ``(provider, provider_id)``."""

    provider: str
    provider_id: str
    email: str
    display_name: str


# Deterministic baseline identities so tests/clients can rely on them.
# - The first is a placeholder (fake provider_id) for data presence only — not loggable.
# - The second is a real Google identity (its `sub`), so it can actually sign in locally
#   as long as the same Google client ID is used.
SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser(Provider.GOOGLE.value, "seed-google-0001", "dev@crew.shop", "Dev User"),
    SeedUser(
        Provider.GOOGLE.value,
        "107265641798951898114",
        "gds.grey@gmail.com",
        "Сергей Самошин",
    ),
)


async def _seed_user(session: AsyncSession, spec: SeedUser) -> bool:
    """Create one seed user if absent. Returns True if created, False if skipped."""
    existing = await session.scalar(
        select(func.count())
        .select_from(OAuthAccount)
        .where(
            OAuthAccount.provider == spec.provider,
            OAuthAccount.provider_id == spec.provider_id,
        )
    )
    if existing:
        logger.info("seed: %s/%s already present — skipped", spec.provider, spec.provider_id)
        return False

    user = User(display_name=spec.display_name, email=spec.email)
    session.add(user)
    await session.flush()
    session.add(
        OAuthAccount(
            user_id=user.id,
            provider=spec.provider,
            provider_id=spec.provider_id,
            provider_email=spec.email,
            provider_name=spec.display_name,
        )
    )
    session.add(UserPreferences(user_id=user.id))
    await session.flush()
    logger.info("seed: created %s (%s/%s)", user.id, spec.provider, spec.provider_id)
    return True


async def seed_users(session: AsyncSession) -> int:
    """Create any missing baseline users (by the OAuth natural key). Returns the count created."""
    created = 0
    for spec in SEED_USERS:
        if await _seed_user(session, spec):
            created += 1
    return created


# ------------------------------------------------------------------------- catalog


@dataclass(frozen=True, slots=True)
class CategorySpec:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class CoffeeSpec:
    name: str
    category: str
    price: Decimal
    region: str
    roast_level: str
    processing: str
    acidity: int
    body: int
    sweetness: int
    flavor_notes: dict[str, list[str]]
    altitude: int | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EquipmentSpec:
    name: str
    category: str
    price: Decimal
    equipment_type: str
    material: str | None = None
    power_watts: int | None = None
    warranty_months: int | None = None
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    depth_cm: Decimal | None = None
    weight_kg: Decimal | None = None
    other_options: dict[str, object] | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class AccessorySpec:
    name: str
    category: str
    price: Decimal
    accessory_type: str
    material: str
    other_options: dict[str, object] | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ConsumableSpec:
    name: str
    category: str
    price: Decimal
    consumable_type: str
    quantity_per_pack: int
    unit_description: str
    material: str | None = None
    expiry_months: int | None = None
    storage_conditions: str | None = None
    other_options: dict[str, object] | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CompatibilitySpec:
    """Links an accessory/consumable to a compatible product (both by seed name)."""

    accessory: str
    compatible: str
    notes: str | None = None


def _flavor_notes(*notes: tuple[str, str, str]) -> dict[str, list[str]]:
    """Build the multilingual flavor-notes object from ``(key, en, ru)`` triples."""
    return {
        "keys": [key for key, _, _ in notes],
        "en": [en for _, en, _ in notes],
        "ru": [ru for _, _, ru in notes],
    }


SEED_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec("Single Origin", "Single-origin specialty coffee beans"),
    CategorySpec("Blends", "Signature house coffee blends"),
    CategorySpec("Equipment", "Machines, grinders and brewers"),
    CategorySpec("Accessories", "Tampers, pitchers and brewing tools"),
    CategorySpec("Consumables", "Filters, pods and cleaning supplies"),
)

SEED_COFFEES: tuple[CoffeeSpec, ...] = (
    CoffeeSpec(
        name="Ethiopia Yirgacheffe",
        category="Single Origin",
        price=Decimal("14.50"),
        region="ethiopia",
        roast_level=RoastLevel.LIGHT,
        processing=ProcessingMethod.WASHED,
        acidity=5,
        body=2,
        sweetness=4,
        altitude=1900,
        flavor_notes=_flavor_notes(
            ("berry", "Berries", "Ягоды"),
            ("floral", "Flowers", "Цветы"),
            ("citrus", "Citrus", "Цитрус"),
        ),
        description="Bright, floral washed Yirgacheffe with a tea-like body.",
    ),
    CoffeeSpec(
        name="Colombia Huila",
        category="Single Origin",
        price=Decimal("12.90"),
        region="colombia",
        roast_level=RoastLevel.MEDIUM,
        processing=ProcessingMethod.WASHED,
        acidity=3,
        body=3,
        sweetness=4,
        altitude=1600,
        flavor_notes=_flavor_notes(
            ("caramel", "Caramel", "Карамель"),
            ("chocolate", "Chocolate", "Шоколад"),
            ("nutty", "Nutty", "Орехи"),
        ),
        description="Balanced and sweet, a crowd-pleasing daily washed Colombian.",
    ),
    CoffeeSpec(
        name="Brazil Cerrado",
        category="Single Origin",
        price=Decimal("11.00"),
        region="brazil",
        roast_level=RoastLevel.DARK,
        processing=ProcessingMethod.NATURAL,
        acidity=2,
        body=5,
        sweetness=3,
        altitude=1100,
        flavor_notes=_flavor_notes(
            ("chocolate", "Chocolate", "Шоколад"),
            ("nutty", "Nutty", "Орехи"),
        ),
        description="Heavy-bodied natural Brazilian, low acidity, great for espresso.",
    ),
    CoffeeSpec(
        name="Kenya Nyeri AA",
        category="Single Origin",
        price=Decimal("15.50"),
        region="kenya",
        roast_level=RoastLevel.MEDIUM,
        processing=ProcessingMethod.WASHED,
        acidity=5,
        body=4,
        sweetness=3,
        altitude=1800,
        flavor_notes=_flavor_notes(
            ("berry", "Berries", "Ягоды"),
            ("citrus", "Citrus", "Цитрус"),
            ("winey", "Winey", "Винный"),
        ),
        description="Intense, juicy Kenyan with blackcurrant acidity.",
    ),
    CoffeeSpec(
        name="House Blend",
        category="Blends",
        price=Decimal("10.50"),
        region="blend",
        roast_level=RoastLevel.MEDIUM,
        processing=ProcessingMethod.NATURAL,
        acidity=3,
        body=4,
        sweetness=4,
        altitude=None,
        flavor_notes=_flavor_notes(
            ("chocolate", "Chocolate", "Шоколад"),
            ("caramel", "Caramel", "Карамель"),
            ("nutty", "Nutty", "Орехи"),
        ),
        description="Comforting everyday blend, chocolatey and smooth.",
    ),
)

SEED_EQUIPMENT: tuple[EquipmentSpec, ...] = (
    EquipmentSpec(
        name="Baratza Encore Grinder",
        category="Equipment",
        price=Decimal("169.00"),
        equipment_type=EquipmentType.GRINDER,
        material="plastic",
        power_watts=165,
        warranty_months=12,
        width_cm=Decimal("12.00"),
        height_cm=Decimal("35.00"),
        depth_cm=Decimal("16.00"),
        weight_kg=Decimal("3.20"),
        other_options={"burr_type": "conical", "colors": ["black"]},
        description="Reliable entry-level conical burr grinder.",
    ),
    EquipmentSpec(
        name="Gaggia Classic Pro",
        category="Equipment",
        price=Decimal("449.00"),
        equipment_type=EquipmentType.MACHINE,
        material="stainless steel",
        power_watts=1425,
        warranty_months=24,
        width_cm=Decimal("23.50"),
        height_cm=Decimal("38.00"),
        depth_cm=Decimal("24.00"),
        weight_kg=Decimal("7.50"),
        other_options={"colors": ["silver"], "portafilter_mm": 58},
        description="Classic single-boiler espresso machine with a 58mm portafilter.",
    ),
    EquipmentSpec(
        name="Hario V60 02 Ceramic",
        category="Equipment",
        price=Decimal("19.90"),
        equipment_type=EquipmentType.BREWER,
        material="ceramic",
        warranty_months=12,
        width_cm=Decimal("13.70"),
        height_cm=Decimal("8.50"),
        depth_cm=Decimal("11.50"),
        weight_kg=Decimal("0.30"),
        other_options={"size": "02", "colors": ["white"]},
        description="Iconic ceramic pour-over dripper, size 02.",
    ),
)

SEED_ACCESSORIES: tuple[AccessorySpec, ...] = (
    AccessorySpec(
        name="Distribution Tamper 58mm",
        category="Accessories",
        price=Decimal("24.90"),
        accessory_type=AccessoryType.TAMPER,
        material="stainless steel",
        other_options={"sizes": ["58mm"]},
        description="Flat-base 58mm tamper for even espresso distribution.",
    ),
    AccessorySpec(
        name="Milk Pitcher 600ml",
        category="Accessories",
        price=Decimal("22.00"),
        accessory_type=AccessoryType.PITCHER,
        material="stainless steel",
        other_options={"capacity_ml": 600},
        description="600ml stainless milk pitcher for latte art.",
    ),
)

SEED_CONSUMABLES: tuple[ConsumableSpec, ...] = (
    ConsumableSpec(
        name="V60 Paper Filters 02 (100pk)",
        category="Consumables",
        price=Decimal("6.50"),
        consumable_type=ConsumableType.FILTER,
        quantity_per_pack=100,
        unit_description="filter",
        material="paper",
        storage_conditions="cool/dry",
        other_options={"size": "02", "models": ["unbleached"]},
        description="Unbleached paper filters for the V60 02 dripper.",
    ),
    ConsumableSpec(
        name="Descaling Tablets (6pk)",
        category="Consumables",
        price=Decimal("9.90"),
        consumable_type=ConsumableType.CLEANING,
        quantity_per_pack=6,
        unit_description="tablet",
        expiry_months=36,
        storage_conditions="room temperature",
        description="Descaling tablets for espresso machines.",
    ),
)

SEED_COMPATIBILITY: tuple[CompatibilitySpec, ...] = (
    CompatibilitySpec(
        accessory="V60 Paper Filters 02 (100pk)",
        compatible="Hario V60 02 Ceramic",
        notes="For size 02 V60 drippers",
    ),
    CompatibilitySpec(
        accessory="Distribution Tamper 58mm",
        compatible="Gaggia Classic Pro",
        notes="Fits the 58mm portafilter",
    ),
)


async def _get_or_create_category(session: AsyncSession, spec: CategorySpec) -> Category:
    category = await session.scalar(select(Category).where(Category.name == spec.name))
    if category is None:
        category = Category(name=spec.name, description=spec.description)
        session.add(category)
        await session.flush()
    return category


async def _get_or_create_product_type(session: AsyncSession, name: ProductTypeName) -> ProductType:
    product_type = await session.scalar(select(ProductType).where(ProductType.name == name.value))
    if product_type is None:
        product_type = ProductType(name=name.value)
        session.add(product_type)
        await session.flush()
    return product_type


async def _get_or_create_product(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    category: Category,
    product_type: ProductType,
    price: Decimal,
    registry: dict[str, Product],
) -> tuple[Product, bool]:
    """Look up a seed product by its (unique-for-seed) name; create the base row if absent."""
    product = await session.scalar(select(Product).where(Product.name == name))
    if product is not None:
        registry[name] = product
        return product, False
    product = Product(
        name=name,
        description=description,
        category_id=category.id,
        product_type_id=product_type.id,
        price=price,
    )
    session.add(product)
    await session.flush()
    registry[name] = product
    return product, True


async def seed_catalog(session: AsyncSession) -> int:
    """Create the baseline catalog (idempotent by natural keys). Returns rows created."""
    categories = {
        spec.name: await _get_or_create_category(session, spec) for spec in SEED_CATEGORIES
    }
    types = {name: await _get_or_create_product_type(session, name) for name in ProductTypeName}
    registry: dict[str, Product] = {}
    created = 0

    for coffee in SEED_COFFEES:
        product, is_new = await _get_or_create_product(
            session,
            name=coffee.name,
            description=coffee.description,
            category=categories[coffee.category],
            product_type=types[ProductTypeName.COFFEE],
            price=coffee.price,
            registry=registry,
        )
        if is_new:
            session.add(
                ProductCoffee(
                    id=product.id,
                    region=coffee.region,
                    roast_level=coffee.roast_level,
                    acidity=coffee.acidity,
                    body=coffee.body,
                    sweetness=coffee.sweetness,
                    processing=coffee.processing,
                    altitude=coffee.altitude,
                    flavor_notes=coffee.flavor_notes,
                )
            )
            created += 1

    for equipment in SEED_EQUIPMENT:
        product, is_new = await _get_or_create_product(
            session,
            name=equipment.name,
            description=equipment.description,
            category=categories[equipment.category],
            product_type=types[ProductTypeName.EQUIPMENT],
            price=equipment.price,
            registry=registry,
        )
        if is_new:
            session.add(
                ProductEquipment(
                    id=product.id,
                    equipment_type=equipment.equipment_type,
                    power_watts=equipment.power_watts,
                    warranty_months=equipment.warranty_months,
                    width_cm=equipment.width_cm,
                    height_cm=equipment.height_cm,
                    depth_cm=equipment.depth_cm,
                    weight_kg=equipment.weight_kg,
                    material=equipment.material,
                    other_options=equipment.other_options,
                )
            )
            created += 1

    for accessory in SEED_ACCESSORIES:
        product, is_new = await _get_or_create_product(
            session,
            name=accessory.name,
            description=accessory.description,
            category=categories[accessory.category],
            product_type=types[ProductTypeName.ACCESSORIES],
            price=accessory.price,
            registry=registry,
        )
        if is_new:
            session.add(
                ProductAccessories(
                    id=product.id,
                    accessory_type=accessory.accessory_type,
                    material=accessory.material,
                    other_options=accessory.other_options,
                )
            )
            created += 1

    for consumable in SEED_CONSUMABLES:
        product, is_new = await _get_or_create_product(
            session,
            name=consumable.name,
            description=consumable.description,
            category=categories[consumable.category],
            product_type=types[ProductTypeName.CONSUMABLES],
            price=consumable.price,
            registry=registry,
        )
        if is_new:
            session.add(
                ProductConsumables(
                    id=product.id,
                    consumable_type=consumable.consumable_type,
                    quantity_per_pack=consumable.quantity_per_pack,
                    unit_description=consumable.unit_description,
                    material=consumable.material,
                    expiry_months=consumable.expiry_months,
                    storage_conditions=consumable.storage_conditions,
                    other_options=consumable.other_options,
                )
            )
            created += 1

    for link in SEED_COMPATIBILITY:
        accessory_product = registry[link.accessory]
        compatible_product = registry[link.compatible]
        existing = await session.scalar(
            select(ProductCompatibility).where(
                ProductCompatibility.accessory_product_id == accessory_product.id,
                ProductCompatibility.compatible_product_id == compatible_product.id,
            )
        )
        if existing is None:
            session.add(
                ProductCompatibility(
                    accessory_product_id=accessory_product.id,
                    compatible_product_id=compatible_product.id,
                    compatibility_notes=link.notes,
                )
            )
            created += 1

    await session.flush()
    return created


async def _run() -> None:
    async with async_session_maker() as session:
        users_created = await seed_users(session)
        catalog_created = await seed_catalog(session)
        await session.commit()
    logger.info(
        "seed summary: users=%d/%d created, catalog rows created=%d",
        users_created,
        len(SEED_USERS),
        catalog_created,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if settings.env not in _ALLOWED_ENVS:
        raise SystemExit(f"seed_dev refuses to run in ENV={settings.env} (dev/test only)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
