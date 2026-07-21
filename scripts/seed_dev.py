"""Idempotent dev/test seed, run by the Docker `init` service after migrations.

Loads a baseline dataset using the ORM models: known dev users (anchored to fixed
crew_auth platform ids, with preferences) and a representative catalog (categories,
product types, products with their type-specific attributes, and compatibility links).
Dev/test only — refuses to run in stage/prod. Re-running is a no-op (idempotent on
natural keys).

Entry point: ``python -m scripts.seed_dev``.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.database import async_session_maker
from src.api.core.utils import utcnow
from src.catalog.enums import (
    AccessoryType,
    ConsumableType,
    EquipmentType,
    ProcessingMethod,
    ProductTypeName,
    RoastLevel,
)
from src.catalog.models import (
    Product,
    ProductAccessories,
    ProductCategory,
    ProductCoffee,
    ProductCompatibility,
    ProductConsumables,
    ProductEquipment,
    ProductType,
)
from src.orders.enums import GrindSize, OrderType
from src.orders.models import Order, OrderPickupInfo, OrderProduct
from src.points.enums import PointType
from src.points.models import Point
from src.ratings.models import Rating
from src.ratings.service import recalculate_product_rating
from src.users.models import User, UserPreferences

logger = logging.getLogger("scripts.seed_dev")

_ALLOWED_ENVS = {"dev", "test"}


# --------------------------------------------------------------------------- users


@dataclass(frozen=True, slots=True)
class SeedUser:
    """A deterministic seed identity, keyed by its crew_auth platform id."""

    auth_user_id: uuid.UUID
    email: str
    display_name: str


# Fixed platform ids so tests and clients can rely on them. These are local placeholders:
# crew_auth mints the real ones, so a seeded user cannot actually sign in unless crew_auth
# happens to issue the same `sub`. They exist to give the dev database populated accounts
# with orders and ratings, not to provide a working login.
DEV_USER_AUTH_ID = uuid.UUID("00000000-0000-4000-8000-00000000d001")
OWNER_USER_AUTH_ID = uuid.UUID("00000000-0000-4000-8000-00000000d002")

SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser(DEV_USER_AUTH_ID, "dev@crew.shop", "Dev User"),
    SeedUser(OWNER_USER_AUTH_ID, "gds.grey@gmail.com", "Сергей Самошин"),
)


async def _seed_user(session: AsyncSession, spec: SeedUser) -> bool:
    """Create one seed user if absent. Returns True if created, False if skipped."""
    existing = await session.scalar(
        select(func.count()).select_from(User).where(User.auth_user_id == spec.auth_user_id)
    )
    if existing:
        logger.info("seed: user %s already present — skipped", spec.auth_user_id)
        return False

    user = User(display_name=spec.display_name, email=spec.email, auth_user_id=spec.auth_user_id)
    session.add(user)
    await session.flush()
    session.add(UserPreferences(user_id=user.id))
    await session.flush()
    logger.info("seed: created user %s (auth_user_id=%s)", user.id, spec.auth_user_id)
    return True


async def seed_users(session: AsyncSession) -> int:
    """Create any missing baseline users (by ``auth_user_id``). Returns the count created."""
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
    product_type: ProductTypeName


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
    CategorySpec("Single Origin", "Single-origin specialty coffee beans", ProductTypeName.COFFEE),
    CategorySpec("Blends", "Signature house coffee blends", ProductTypeName.COFFEE),
    CategorySpec("Equipment", "Machines, grinders and brewers", ProductTypeName.EQUIPMENT),
    CategorySpec("Accessories", "Tampers, pitchers and brewing tools", ProductTypeName.ACCESSORIES),
    CategorySpec("Consumables", "Filters, pods and cleaning supplies", ProductTypeName.CONSUMABLES),
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

# ------------------------------------------------------------- generated bulk catalog
#
# The curated specs above stay as-is (compatibility/ratings reference them by name).
# The generators below append ~10x more products so the catalog endpoints can be
# exercised against a realistic volume (~120 products) for pagination. Generated
# coffees deliberately avoid the regions/roasts/flavours/acidity the curated filter
# tests assert on, so those exact-match tests stay valid; non-coffee products never
# appear in coffee-filtered results at all.

# (region, display) — none overlap the curated ethiopia/colombia/kenya filter fixtures.
_GEN_COFFEE_ORIGINS: tuple[tuple[str, str, str], ...] = (
    ("guatemala", "Guatemala", "13.00"),
    ("rwanda", "Rwanda", "14.00"),
    ("peru", "Peru", "11.50"),
    ("honduras", "Honduras", "10.90"),
    ("costa-rica", "Costa Rica", "14.50"),
    ("panama", "Panama", "16.00"),
    ("mexico", "Mexico", "11.80"),
    ("ecuador", "Ecuador", "12.40"),
    ("indonesia", "Indonesia", "13.70"),
)

# Flavour pool excludes "berry" (a curated filter fixture).
_GEN_FLAVOR_POOL: tuple[tuple[str, str, str], ...] = (
    ("caramel", "Caramel", "Карамель"),
    ("chocolate", "Chocolate", "Шоколад"),
    ("nutty", "Nutty", "Орехи"),
    ("floral", "Flowers", "Цветы"),
    ("citrus", "Citrus", "Цитрус"),
    ("winey", "Winey", "Винный"),
    ("stone-fruit", "Stone fruit", "Косточковые"),
    ("honey", "Honey", "Мёд"),
)

_GEN_MATERIALS: tuple[str, ...] = ("stainless steel", "plastic", "aluminium", "ceramic", "glass")


def _generate_coffees() -> list[CoffeeSpec]:
    # medium/dark only and acidity 1-3 keep generated coffees out of the curated
    # light-roast and "bright" acidity filter fixtures.
    roasts = (RoastLevel.MEDIUM, RoastLevel.DARK)
    processes = list(ProcessingMethod)
    out: list[CoffeeSpec] = []
    i = 0
    for region, display, base in _GEN_COFFEE_ORIGINS:
        base_price = Decimal(base)
        for lot in range(1, 6):
            notes = tuple(_GEN_FLAVOR_POOL[(i + k) % len(_GEN_FLAVOR_POOL)] for k in range(3))
            out.append(
                CoffeeSpec(
                    name=f"{display} Micro-lot {lot:02d}",
                    category="Single Origin",
                    price=base_price + Decimal(lot),
                    region=region,
                    roast_level=roasts[i % len(roasts)],
                    processing=processes[i % len(processes)],
                    acidity=1 + (i % 3),
                    body=1 + ((i + 2) % 5),
                    sweetness=1 + ((i + 1) % 5),
                    altitude=1000 + (i % 12) * 100,
                    flavor_notes=_flavor_notes(*notes),
                    description=f"Seeded {display} micro-lot {lot} for pagination testing.",
                )
            )
            i += 1
    return out


def _generate_equipment() -> list[EquipmentSpec]:
    types = list(EquipmentType)
    out: list[EquipmentSpec] = []
    for n in range(27):
        etype = types[n % len(types)]
        powered = etype in (EquipmentType.MACHINE, EquipmentType.GRINDER)
        out.append(
            EquipmentSpec(
                name=f"Crew {etype.value.capitalize()} {n + 1:02d}",
                category="Equipment",
                price=Decimal("49.00") + Decimal(n) * Decimal("10.00"),
                equipment_type=etype,
                material=_GEN_MATERIALS[n % len(_GEN_MATERIALS)],
                power_watts=(100 + (n % 15) * 100) if powered else None,
                warranty_months=12 + (n % 3) * 12,
                weight_kg=Decimal("1.00") + Decimal(n % 8),
                other_options={"sku": f"EQ-{n + 1:03d}"},
                description=f"Seeded {etype.value} unit {n + 1} for pagination testing.",
            )
        )
    return out


def _generate_accessories() -> list[AccessorySpec]:
    types = list(AccessoryType)
    out: list[AccessorySpec] = []
    for n in range(18):
        atype = types[n % len(types)]
        out.append(
            AccessorySpec(
                name=f"Crew {atype.value.capitalize()} {n + 1:02d}",
                category="Accessories",
                price=Decimal("9.00") + Decimal(n) * Decimal("2.50"),
                accessory_type=atype,
                material=_GEN_MATERIALS[n % len(_GEN_MATERIALS)],
                other_options={"sku": f"AC-{n + 1:03d}"},
                description=f"Seeded {atype.value} {n + 1} for pagination testing.",
            )
        )
    return out


def _generate_consumables() -> list[ConsumableSpec]:
    types = list(ConsumableType)
    units = ("filter", "pod", "tablet", "sachet", "bottle")
    out: list[ConsumableSpec] = []
    for n in range(18):
        ctype = types[n % len(types)]
        out.append(
            ConsumableSpec(
                name=f"Crew {ctype.value.capitalize()} Pack {n + 1:02d}",
                category="Consumables",
                price=Decimal("4.50") + Decimal(n) * Decimal("1.50"),
                consumable_type=ctype,
                quantity_per_pack=10 * (1 + n % 10),
                unit_description=units[n % len(units)],
                material="paper" if ctype == ConsumableType.FILTER else None,
                expiry_months=12 + (n % 4) * 6,
                storage_conditions="cool/dry",
                other_options={"sku": f"CO-{n + 1:03d}"},
                description=f"Seeded {ctype.value} pack {n + 1} for pagination testing.",
            )
        )
    return out


SEED_COFFEES = SEED_COFFEES + tuple(_generate_coffees())
SEED_EQUIPMENT = SEED_EQUIPMENT + tuple(_generate_equipment())
SEED_ACCESSORIES = SEED_ACCESSORIES + tuple(_generate_accessories())
SEED_CONSUMABLES = SEED_CONSUMABLES + tuple(_generate_consumables())


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


async def _get_or_create_category(session: AsyncSession, spec: CategorySpec) -> ProductCategory:
    category = await session.scalar(
        select(ProductCategory).where(ProductCategory.name == spec.name)
    )
    if category is None:
        product_type = await _get_or_create_product_type(session, spec.product_type)
        category = ProductCategory(
            name=spec.name, description=spec.description, product_type_id=product_type.id
        )
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
    category: ProductCategory,
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
        product_category_id=category.id,
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


# ------------------------------------------------------------------------- ratings


@dataclass(frozen=True, slots=True)
class RatingSpec:
    """A seed rating: a seed user (by ``auth_user_id``) rating a product (by name)."""

    product: str
    auth_user_id: uuid.UUID
    score: int


# A subset of products is rated by the seed users; the rest stay unrated so the catalog
# exercises both the "has rating" and "no rating" paths.
SEED_RATINGS: tuple[RatingSpec, ...] = (
    RatingSpec("Ethiopia Yirgacheffe", DEV_USER_AUTH_ID, 5),
    RatingSpec("Ethiopia Yirgacheffe", OWNER_USER_AUTH_ID, 4),
    RatingSpec("Colombia Huila", DEV_USER_AUTH_ID, 4),
    RatingSpec("Colombia Huila", OWNER_USER_AUTH_ID, 4),
    RatingSpec("Brazil Cerrado", DEV_USER_AUTH_ID, 3),
    RatingSpec("Kenya Nyeri AA", OWNER_USER_AUTH_ID, 5),
    RatingSpec("Gaggia Classic Pro", DEV_USER_AUTH_ID, 5),
    RatingSpec("Gaggia Classic Pro", OWNER_USER_AUTH_ID, 4),
    RatingSpec("Baratza Encore Grinder", DEV_USER_AUTH_ID, 4),
)


async def seed_ratings(session: AsyncSession) -> int:
    """Create seed ratings and rebuild the affected aggregates. Idempotent per (product, user)."""
    user_by_auth_id = {
        auth_user_id: user_id
        for auth_user_id, user_id in (
            await session.execute(
                select(User.auth_user_id, User.id).where(User.auth_user_id.is_not(None))
            )
        ).all()
    }
    product_ids: dict[str, uuid.UUID | None] = {}
    affected: set[uuid.UUID] = set()
    created = 0

    for spec in SEED_RATINGS:
        if spec.product not in product_ids:
            product_ids[spec.product] = await session.scalar(
                select(Product.id).where(Product.name == spec.product)
            )
        product_id = product_ids[spec.product]
        user_id = user_by_auth_id.get(spec.auth_user_id)
        if product_id is None or user_id is None:
            continue
        exists = await session.scalar(
            select(Rating.id).where(Rating.product_id == product_id, Rating.user_id == user_id)
        )
        if exists is not None:
            continue
        session.add(Rating(product_id=product_id, user_id=user_id, rating=spec.score))
        affected.add(product_id)
        created += 1

    await session.flush()
    for product_id in affected:
        await recalculate_product_rating(session, product_id)
    return created


# -------------------------------------------------------------------------- points

_WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True, slots=True)
class PointSpec:
    name: str
    address: str
    type: str
    hours: dict[str, Any]
    contacts: dict[str, Any]


SEED_POINTS: tuple[PointSpec, ...] = (
    PointSpec(
        name="Crew Coffee Downtown",
        address="vul. Khreshchatyk 1, Kyiv",
        type=PointType.COFFEESHOP,
        hours={day: {"open": "08:00", "close": "20:00"} for day in _WEEK},
        contacts={"phone": "+380441234567", "email": "downtown@crew.shop"},
    ),
)


async def seed_points(session: AsyncSession) -> int:
    """Create the baseline pickup points (idempotent by name). Returns the count created."""
    created = 0
    for spec in SEED_POINTS:
        existing = await session.scalar(select(Point.id).where(Point.name == spec.name))
        if existing is not None:
            continue
        session.add(
            Point(
                name=spec.name,
                address=spec.address,
                type=spec.type,
                hours=spec.hours,
                contacts=spec.contacts,
            )
        )
        created += 1
    await session.flush()
    return created


# -------------------------------------------------------------------------- orders


@dataclass(frozen=True, slots=True)
class OrderItemSpec:
    """A line item by seed product name; ``grind`` only for coffee."""

    product: str
    quantity: int
    grind: str | None = None


@dataclass(frozen=True, slots=True)
class OrderSpec:
    """A sample pickup order: a seed user, a seed point, and items. Keyed by ``pickup_code``."""

    auth_user_id: uuid.UUID
    point: str
    pickup_code: str
    items: tuple[OrderItemSpec, ...]


SEED_ORDERS: tuple[OrderSpec, ...] = (
    OrderSpec(
        auth_user_id=DEV_USER_AUTH_ID,
        point="Crew Coffee Downtown",
        pickup_code="100001",
        items=(
            OrderItemSpec("Ethiopia Yirgacheffe", 2, GrindSize.MEDIUM),
            OrderItemSpec("Hario V60 02 Ceramic", 1),
        ),
    ),
)


async def seed_orders(session: AsyncSession) -> int:
    """Create sample pickup orders (idempotent by ``pickup_code``). Returns the count created."""
    created = 0
    for spec in SEED_ORDERS:
        exists = await session.scalar(
            select(OrderPickupInfo.id).where(OrderPickupInfo.pickup_code == spec.pickup_code)
        )
        if exists is not None:
            continue
        user_id = await session.scalar(
            select(User.id).where(User.auth_user_id == spec.auth_user_id)
        )
        point_id = await session.scalar(select(Point.id).where(Point.name == spec.point))
        if user_id is None or point_id is None:
            continue

        line_rows: list[OrderProduct] = []
        total = Decimal("0.00")
        for item in spec.items:
            product = await session.scalar(select(Product).where(Product.name == item.product))
            if product is None:
                break
            total += product.price * item.quantity
            line_rows.append(
                OrderProduct(
                    product_id=product.id,
                    product_name=product.name,
                    product_price=product.price,
                    quantity=item.quantity,
                    grind=item.grind,
                )
            )
        if len(line_rows) != len(spec.items):
            continue

        order = Order(
            user_id=user_id,
            order_type=OrderType.PICKUP,
            total_price=total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        order.products = line_rows
        order.pickup_info = OrderPickupInfo(
            point_id=point_id,
            pickup_code=spec.pickup_code,
            pickup_deadline=utcnow() + timedelta(hours=24),
        )
        session.add(order)
        created += 1

    await session.flush()
    return created


async def _run() -> None:
    async with async_session_maker() as session:
        users_created = await seed_users(session)
        catalog_created = await seed_catalog(session)
        ratings_created = await seed_ratings(session)
        points_created = await seed_points(session)
        orders_created = await seed_orders(session)
        await session.commit()
    logger.info(
        "seed summary: users=%d/%d created, catalog rows=%d, ratings=%d, points=%d, orders=%d",
        users_created,
        len(SEED_USERS),
        catalog_created,
        ratings_created,
        points_created,
        orders_created,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if settings.env not in _ALLOWED_ENVS:
        raise SystemExit(f"seed_dev refuses to run in ENV={settings.env} (dev/test only)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
