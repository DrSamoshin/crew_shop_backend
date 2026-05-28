"""Customer subscription endpoints: create + lifecycle, scoped to the caller."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import require_auth
from src.subscriptions.schemas import (
    CreateSubscriptionRequest,
    SubscriptionDTO,
    SubscriptionListDTO,
)
from src.subscriptions.service import SubscriptionService
from src.users.models import User

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.post(
    "",
    response_model=SubscriptionDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a subscription",
)
async def create_subscription(
    payload: CreateSubscriptionRequest, db: DbDep, user: UserDep
) -> SubscriptionDTO:
    return await SubscriptionService(db).create(user.id, payload)


@router.get("", response_model=SubscriptionListDTO, summary="List the caller's subscriptions")
async def list_subscriptions(db: DbDep, user: UserDep) -> SubscriptionListDTO:
    return await SubscriptionService(db).list_for_user(user.id)


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionDTO,
    summary="Get subscription detail",
)
async def get_subscription(subscription_id: uuid.UUID, db: DbDep, user: UserDep) -> SubscriptionDTO:
    return await SubscriptionService(db).get(subscription_id, user.id)


@router.post(
    "/{subscription_id}/pause",
    response_model=SubscriptionDTO,
    summary="Pause an active subscription",
)
async def pause_subscription(
    subscription_id: uuid.UUID, db: DbDep, user: UserDep
) -> SubscriptionDTO:
    return await SubscriptionService(db).pause(subscription_id, user.id)


@router.post(
    "/{subscription_id}/resume",
    response_model=SubscriptionDTO,
    summary="Resume a paused subscription",
)
async def resume_subscription(
    subscription_id: uuid.UUID, db: DbDep, user: UserDep
) -> SubscriptionDTO:
    return await SubscriptionService(db).resume(subscription_id, user.id)


@router.post(
    "/{subscription_id}/cancel",
    response_model=SubscriptionDTO,
    summary="Cancel a subscription",
)
async def cancel_subscription(
    subscription_id: uuid.UUID, db: DbDep, user: UserDep
) -> SubscriptionDTO:
    return await SubscriptionService(db).cancel(subscription_id, user.id)
