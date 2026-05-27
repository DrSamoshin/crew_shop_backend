"""Customer order endpoints: create, list own orders, detail, cancel.

All endpoints require a bearer access token; ownership is enforced on detail and cancel.
The staff/system status update lives on the S2S-gated admin router. Errors flow through the
shared AppException envelope.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import require_auth
from src.orders.enums import OrderStatus
from src.orders.schemas import CreateOrderRequest, OrderDTO, OrderListDTO
from src.orders.service import OrderService
from src.users.models import User

router = APIRouter(prefix="/orders", tags=["orders"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.post(
    "", response_model=OrderDTO, status_code=status.HTTP_201_CREATED, summary="Create order"
)
async def create_order(payload: CreateOrderRequest, db: DbDep, user: UserDep) -> OrderDTO:
    return await OrderService(db).create(user.id, payload)


@router.get("", response_model=OrderListDTO, summary="List the caller's orders")
async def list_orders(
    db: DbDep,
    user: UserDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: OrderStatus | None = None,
) -> OrderListDTO:
    return await OrderService(db).list_orders(user.id, status, limit, offset)


@router.get("/{order_id}", response_model=OrderDTO, summary="Get order detail")
async def get_order(order_id: uuid.UUID, db: DbDep, user: UserDep) -> OrderDTO:
    return await OrderService(db).get(order_id, user.id)


@router.post("/{order_id}/cancel", response_model=OrderDTO, summary="Cancel a created order")
async def cancel_order(order_id: uuid.UUID, db: DbDep, user: UserDep) -> OrderDTO:
    return await OrderService(db).cancel(order_id, user.id)
