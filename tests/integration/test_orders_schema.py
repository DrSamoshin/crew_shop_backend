"""Integration tests for the orders schema (orders, line items, pickup/delivery info, points)."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from scripts import seed_dev
from src.api.core.utils import utcnow
from src.catalog.models import Category, Product, ProductType
from src.orders.models import Order, OrderDeliveryInfo, OrderPickupInfo, OrderProduct
from src.points.models import Point
from src.users.models import User


async def _make_user(session: AsyncSession, name: str = "Buyer") -> User:
    user = User(display_name=name)
    session.add(user)
    await session.flush()
    return user


async def _make_point(
    session: AsyncSession, *, type_: str = "coffeeshop", name: str = "Shop"
) -> Point:
    point = Point(name=name, address="vul. Test 1", type=type_, hours={}, contacts={})
    session.add(point)
    await session.flush()
    return point


async def _make_product(
    session: AsyncSession, *, name: str = "Prod", price: Decimal = Decimal("10.00")
) -> Product:
    category = Category(name=f"cat-{uuid.uuid4()}")
    product_type = ProductType(name=f"type-{uuid.uuid4()}")
    session.add_all([category, product_type])
    await session.flush()
    product = Product(
        name=name, category_id=category.id, product_type_id=product_type.id, price=price
    )
    session.add(product)
    await session.flush()
    return product


async def _pickup_order(session: AsyncSession) -> Order:
    """A complete pickup order: two line items (coffee with grind + brewer) and pickup info."""
    user = await _make_user(session)
    point = await _make_point(session)
    coffee = await _make_product(session, name="Coffee", price=Decimal("12.50"))
    brewer = await _make_product(session, name="Brewer", price=Decimal("20.00"))
    order = Order(
        user_id=user.id, order_type="pickup", total_price=Decimal("45.00"), notes="ring the bell"
    )
    order.products = [
        OrderProduct(
            product_id=coffee.id,
            product_name=coffee.name,
            product_price=coffee.price,
            quantity=2,
            grind="medium",
        ),
        OrderProduct(
            product_id=brewer.id,
            product_name=brewer.name,
            product_price=brewer.price,
            quantity=1,
            grind=None,
        ),
    ]
    order.pickup_info = OrderPickupInfo(
        point_id=point.id, pickup_code="123456", pickup_deadline=utcnow() + timedelta(hours=24)
    )
    session.add(order)
    await session.flush()
    return order


async def test_create_pickup_order_defaults(db_session: AsyncSession) -> None:
    order = await _pickup_order(db_session)
    await db_session.refresh(order)

    assert order.status == "created"  # server default
    assert order.currency == "EUR"  # server default
    assert order.created_at is not None

    line_count = await db_session.scalar(
        select(func.count()).select_from(OrderProduct).where(OrderProduct.order_id == order.id)
    )
    assert line_count == 2


async def test_create_delivery_order(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    product = await _make_product(db_session, price=Decimal("8.00"))
    order = Order(user_id=user.id, order_type="delivery", total_price=Decimal("16.00"))
    order.products = [
        OrderProduct(
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            quantity=2,
        )
    ]
    order.delivery_info = OrderDeliveryInfo(
        recipient_name="John Doe",
        phone="+380501234567",
        address="vul. Khreshchatyk 1",
        city="Kyiv",
        postal_code=None,  # optional
    )
    db_session.add(order)
    await db_session.flush()
    await db_session.refresh(order)

    assert order.order_type == "delivery"
    info = await db_session.scalar(
        select(OrderDeliveryInfo).where(OrderDeliveryInfo.order_id == order.id)
    )
    assert info is not None
    assert info.postal_code is None
    assert info.shipped_at is None


async def test_invalid_order_type_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    db_session.add(Order(user_id=user.id, order_type="mail", total_price=Decimal("1.00")))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_status_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    db_session.add(
        Order(user_id=user.id, order_type="pickup", total_price=Decimal("1.00"), status="paid")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_non_positive_total_price_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    db_session.add(Order(user_id=user.id, order_type="pickup", total_price=Decimal("0.00")))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_non_positive_quantity_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    product = await _make_product(db_session)
    order = Order(user_id=user.id, order_type="pickup", total_price=Decimal("10.00"))
    order.products = [
        OrderProduct(
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            quantity=0,
        )
    ]
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_grind_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    product = await _make_product(db_session)
    order = Order(user_id=user.id, order_type="pickup", total_price=Decimal("10.00"))
    order.products = [
        OrderProduct(
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            quantity=1,
            grind="powder",
        )
    ]
    db_session.add(order)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_point_type_rejected(db_session: AsyncSession) -> None:
    db_session.add(Point(name="X", address="a", type="bistro", hours={}, contacts={}))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_pickup_info_per_order(db_session: AsyncSession) -> None:
    order = await _pickup_order(db_session)
    point = await _make_point(db_session, name="Second")
    db_session.add(
        OrderPickupInfo(
            order_id=order.id,
            point_id=point.id,
            pickup_code="654321",
            pickup_deadline=utcnow() + timedelta(hours=24),
        )
    )
    with pytest.raises(IntegrityError):  # UNIQUE(order_id)
        await db_session.flush()


async def test_duplicate_pickup_code_rejected(db_session: AsyncSession) -> None:
    await _pickup_order(db_session)  # uses code 123456
    user = await _make_user(db_session, name="Other")
    point = await _make_point(db_session, name="Other Shop")
    order = Order(user_id=user.id, order_type="pickup", total_price=Decimal("5.00"))
    order.pickup_info = OrderPickupInfo(
        point_id=point.id, pickup_code="123456", pickup_deadline=utcnow() + timedelta(hours=24)
    )
    db_session.add(order)
    with pytest.raises(IntegrityError):  # UNIQUE(pickup_code)
        await db_session.flush()


async def test_delete_order_cascades_products_and_info(db_session: AsyncSession) -> None:
    order = await _pickup_order(db_session)
    order_id = order.id

    await db_session.delete(order)
    await db_session.flush()

    products = await db_session.scalar(
        select(func.count()).select_from(OrderProduct).where(OrderProduct.order_id == order_id)
    )
    pickups = await db_session.scalar(
        select(func.count())
        .select_from(OrderPickupInfo)
        .where(OrderPickupInfo.order_id == order_id)
    )
    assert products == 0
    assert pickups == 0


async def test_user_delete_restricted_with_orders(db_session: AsyncSession) -> None:
    order = await _pickup_order(db_session)
    user = await db_session.get(User, order.user_id)
    assert user is not None
    await db_session.delete(user)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await db_session.flush()


async def test_product_delete_restricted_when_ordered(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    product = await _make_product(db_session)
    order = Order(user_id=user.id, order_type="pickup", total_price=Decimal("10.00"))
    order.products = [
        OrderProduct(
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            quantity=1,
        )
    ]
    db_session.add(order)
    await db_session.flush()

    await db_session.delete(product)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await db_session.flush()


async def test_point_delete_restricted_when_referenced(db_session: AsyncSession) -> None:
    order = await _pickup_order(db_session)
    pickup = await db_session.scalar(
        select(OrderPickupInfo).where(OrderPickupInfo.order_id == order.id)
    )
    assert pickup is not None
    point = await db_session.get(Point, pickup.point_id)
    assert point is not None
    await db_session.delete(point)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT
        await db_session.flush()


async def test_seed_points_and_orders_idempotent(db_session: AsyncSession) -> None:
    await seed_dev.seed_users(db_session)
    await seed_dev.seed_catalog(db_session)

    points_first = await seed_dev.seed_points(db_session)
    orders_first = await seed_dev.seed_orders(db_session)
    points_again = await seed_dev.seed_points(db_session)
    orders_again = await seed_dev.seed_orders(db_session)

    assert points_first == len(seed_dev.SEED_POINTS)
    assert orders_first == len(seed_dev.SEED_ORDERS)
    assert points_again == 0
    assert orders_again == 0

    assert await db_session.scalar(select(func.count()).select_from(Point)) == len(
        seed_dev.SEED_POINTS
    )
    assert await db_session.scalar(select(func.count()).select_from(Order)) == len(
        seed_dev.SEED_ORDERS
    )
