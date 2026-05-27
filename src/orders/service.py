"""Order service: validation, price snapshotting, fulfillment, and status transitions.

Creating an order validates the products (exist + active), snapshots each name/price, computes
the EUR total, and creates exactly one fulfillment row (pickup with a unique 6-digit code and a
24h deadline, or delivery with the captured address). Reads enforce ownership; staff status
updates run through the generic transition machine and stamp the matching info-table milestone.
"""

import secrets
import uuid
from collections.abc import Sequence
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.utils import utcnow
from src.catalog.models import Product
from src.orders.enums import OrderStatus, OrderType
from src.orders.exceptions import (
    OrderAccessDeniedError,
    OrderInvalidItemsError,
    OrderInvalidStatusTransitionError,
    OrderNotFoundError,
    OrderPickupPointNotFoundError,
    OrderPickupPointUnavailableError,
    OrderProductInactiveError,
    OrderProductNotFoundError,
)
from src.orders.models import Order, OrderDeliveryInfo, OrderPickupInfo, OrderProduct
from src.orders.repository import OrderRepository
from src.orders.schemas import (
    CreateOrderRequest,
    DeliveryInfoDTO,
    OrderDTO,
    OrderItemDTO,
    OrderItemIn,
    OrderListDTO,
    OrderListItemDTO,
    PickupInfoDTO,
)
from src.orders.status import STAFF_TARGETS, ensure_transition
from src.points.enums import PointType
from src.points.models import Point

_PICKUP_TTL = timedelta(hours=24)
_PICKUP_CODE_ATTEMPTS = 10


def _item_dto(item: OrderProduct) -> OrderItemDTO:
    return OrderItemDTO(
        id=item.id,
        product_id=item.product_id,
        product_name=item.product_name,
        product_price=item.product_price,
        quantity=item.quantity,
        grind=item.grind,
        subtotal=item.product_price * item.quantity,
    )


def _pickup_dto(info: OrderPickupInfo) -> PickupInfoDTO:
    return PickupInfoDTO(
        point_id=info.point_id,
        point_name=info.point.name,
        point_address=info.point.address,
        pickup_code=info.pickup_code,
        pickup_deadline=info.pickup_deadline,
        picked_up_at=info.picked_up_at,
    )


def _delivery_dto(info: OrderDeliveryInfo) -> DeliveryInfoDTO:
    return DeliveryInfoDTO(
        recipient_name=info.recipient_name,
        phone=info.phone,
        address=info.address,
        city=info.city,
        postal_code=info.postal_code,
        notes=info.notes,
        shipped_at=info.shipped_at,
        delivered_at=info.delivered_at,
    )


def _order_dto(order: Order) -> OrderDTO:
    return OrderDTO(
        id=order.id,
        user_id=order.user_id,
        order_type=order.order_type,
        status=order.status,
        total_price=order.total_price,
        currency=order.currency,
        notes=order.notes,
        items=[_item_dto(item) for item in order.products],
        pickup=_pickup_dto(order.pickup_info) if order.pickup_info else None,
        delivery=_delivery_dto(order.delivery_info) if order.delivery_info else None,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _list_item_dto(order: Order) -> OrderListItemDTO:
    return OrderListItemDTO(
        id=order.id,
        user_id=order.user_id,
        order_type=order.order_type,
        status=order.status,
        total_price=order.total_price,
        item_count=len(order.products),
        pickup_point_name=order.pickup_info.point.name if order.pickup_info else None,
        delivery_city=order.delivery_info.city if order.delivery_info else None,
        created_at=order.created_at,
    )


class OrderService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = OrderRepository(db)

    async def create(self, user_id: uuid.UUID, data: CreateOrderRequest) -> OrderDTO:
        if not data.items:  # defensive; the schema also enforces a non-empty list
            raise OrderInvalidItemsError()

        products = await self._load_active_products(data.items)
        total = Decimal("0.00")
        line_items: list[OrderProduct] = []
        for item in data.items:
            product = products[item.product_id]
            total += product.price * item.quantity
            line_items.append(
                OrderProduct(
                    product_id=product.id,
                    product_name=product.name,
                    product_price=product.price,
                    quantity=item.quantity,
                    grind=item.grind.value if item.grind else None,
                )
            )

        order = Order(
            user_id=user_id,
            order_type=data.order_type.value,
            total_price=total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        order.products = line_items

        if data.order_type is OrderType.PICKUP:
            assert data.pickup_point_id is not None  # guaranteed by schema validation
            await self._require_available_point(data.pickup_point_id)
            order.pickup_info = OrderPickupInfo(
                point_id=data.pickup_point_id,
                pickup_code=await self._allocate_pickup_code(),
                pickup_deadline=utcnow() + _PICKUP_TTL,
            )
        else:
            assert data.delivery is not None  # guaranteed by schema validation
            d = data.delivery
            order.delivery_info = OrderDeliveryInfo(
                recipient_name=d.recipient_name,
                phone=d.phone,
                address=d.address,
                city=d.city,
                postal_code=d.postal_code,
                notes=d.delivery_notes,
            )

        await self._repo.add(order)
        return _order_dto(await self._reload(order.id))

    async def list_orders(
        self,
        user_id: uuid.UUID,
        status: OrderStatus | None,
        limit: int,
        offset: int,
    ) -> OrderListDTO:
        orders, total = await self._repo.list_for_user(
            user_id, status.value if status else None, limit, offset
        )
        return OrderListDTO(
            items=[_list_item_dto(order) for order in orders],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get(self, order_id: uuid.UUID, user_id: uuid.UUID) -> OrderDTO:
        order = await self._require_owned(order_id, user_id)
        return _order_dto(order)

    async def cancel(self, order_id: uuid.UUID, user_id: uuid.UUID) -> OrderDTO:
        order = await self._require_owned(order_id, user_id)
        ensure_transition(OrderStatus(order.status), OrderStatus.CANCELLED)
        order.status = OrderStatus.CANCELLED.value
        await self._db.flush()
        return _order_dto(await self._reload(order_id))

    async def update_status(self, order_id: uuid.UUID, target: OrderStatus) -> OrderDTO:
        order = await self._repo.get(order_id)
        if order is None:
            raise OrderNotFoundError(str(order_id))
        current = OrderStatus(order.status)
        if target not in STAFF_TARGETS:
            raise OrderInvalidStatusTransitionError(current.value, target.value)
        ensure_transition(current, target)
        order.status = target.value
        self._stamp_milestone(order, target)
        await self._db.flush()
        return _order_dto(await self._reload(order_id))

    # ------------------------------------------------------------------ helpers

    async def _reload(self, order_id: uuid.UUID) -> Order:
        order = await self._repo.get(order_id)
        assert order is not None  # just written/updated in this session
        return order

    async def _require_owned(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Order:
        order = await self._repo.get(order_id)
        if order is None:
            raise OrderNotFoundError(str(order_id))
        if order.user_id != user_id:
            raise OrderAccessDeniedError()
        return order

    async def _load_active_products(self, items: Sequence[OrderItemIn]) -> dict[uuid.UUID, Product]:
        ids = {item.product_id for item in items}
        rows = (await self._db.execute(select(Product).where(Product.id.in_(ids)))).scalars().all()
        by_id = {product.id: product for product in rows}
        for item in items:
            product = by_id.get(item.product_id)
            if product is None:
                raise OrderProductNotFoundError(str(item.product_id))
            if not product.is_active:
                raise OrderProductInactiveError(str(item.product_id))
        return by_id

    async def _require_available_point(self, point_id: uuid.UUID) -> Point:
        point = await self._db.get(Point, point_id)
        if point is None:
            raise OrderPickupPointNotFoundError(str(point_id))
        if not point.is_active or point.type != PointType.COFFEESHOP.value:
            raise OrderPickupPointUnavailableError(str(point_id))
        return point

    async def _allocate_pickup_code(self) -> str:
        for _ in range(_PICKUP_CODE_ATTEMPTS):
            code = f"{secrets.randbelow(1_000_000):06d}"
            if not await self._repo.pickup_code_exists(code):
                return code
        raise RuntimeError("could not allocate a unique pickup code")

    @staticmethod
    def _stamp_milestone(order: Order, target: OrderStatus) -> None:
        """Record the fulfillment milestone implied by a status change (idempotent)."""
        now = utcnow()
        if target is OrderStatus.IN_PROGRESS:
            if order.delivery_info and order.delivery_info.shipped_at is None:
                order.delivery_info.shipped_at = now
        elif target is OrderStatus.COMPLETED:
            if order.pickup_info and order.pickup_info.picked_up_at is None:
                order.pickup_info.picked_up_at = now
            if order.delivery_info and order.delivery_info.delivered_at is None:
                order.delivery_info.delivered_at = now
