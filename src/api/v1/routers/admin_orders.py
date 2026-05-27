"""Admin (S2S-gated) order operations: staff/system status updates.

Trusted only for a backend service (e.g. crew_admin): every request carries the per-environment
service token, and the acting operator/role is recorded for audit. Advancing the status stamps
the matching fulfillment milestone (shipped/delivered/picked up). Customer-facing order
endpoints live on the user-authenticated ``/v1/orders`` router.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.orders.admin.dependencies import ServiceCaller, audit, require_service_caller
from src.orders.schemas import OrderDTO, UpdateOrderStatusRequest
from src.orders.service import OrderService

router = APIRouter(prefix="/admin/orders", tags=["orders-admin"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
CallerDep = Annotated[ServiceCaller, Depends(require_service_caller)]


@router.post("/{order_id}/status", response_model=OrderDTO, summary="Update order status")
async def update_order_status(
    order_id: uuid.UUID, payload: UpdateOrderStatusRequest, db: DbDep, caller: CallerDep
) -> OrderDTO:
    order = await OrderService(db).update_status(order_id, payload.status)
    audit(caller, f"status:{payload.status.value}", f"order:{order_id}")
    return order
