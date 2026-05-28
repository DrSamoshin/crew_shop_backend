"""Saved payment-method endpoints, scoped to the caller (``/v1/users/me/payment-methods``)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import require_auth
from src.payments import method_service
from src.payments.method_schemas import (
    PaymentMethodDTO,
    PaymentMethodListDTO,
    SavePaymentMethodRequest,
)
from src.payments.provider import PaymentProviderDep
from src.users.models import User

router = APIRouter(prefix="/users/me/payment-methods", tags=["payment-methods"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.post(
    "",
    response_model=PaymentMethodDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Save a payment method from a provider intent token",
)
async def save_method(
    payload: SavePaymentMethodRequest,
    db: DbDep,
    user: UserDep,
    provider: PaymentProviderDep,
) -> PaymentMethodDTO:
    return await method_service.save_method(db, provider, user.id, payload)


@router.get(
    "",
    response_model=PaymentMethodListDTO,
    summary="List the caller's saved payment methods",
)
async def list_methods(db: DbDep, user: UserDep) -> PaymentMethodListDTO:
    return await method_service.list_methods(db, user.id)


@router.post(
    "/{method_id}/default",
    response_model=PaymentMethodDTO,
    summary="Make this method the caller's default",
)
async def set_default(method_id: uuid.UUID, db: DbDep, user: UserDep) -> PaymentMethodDTO:
    return await method_service.set_default(db, user.id, method_id)


@router.delete(
    "/{method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a saved payment method",
)
async def delete_method(
    method_id: uuid.UUID, db: DbDep, user: UserDep, provider: PaymentProviderDep
) -> None:
    await method_service.delete_method(db, provider, user.id, method_id)
