"""Saved payment methods service.

The provider holds the secrets (PCI-compliant token / customer); we store opaque ids plus
display fields (brand / last4 / exp). ``set_default`` maintains the at-most-one-default
invariant per user.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.payments.exceptions import PaymentMethodNotFoundError
from src.payments.method_schemas import (
    PaymentMethodDTO,
    PaymentMethodListDTO,
    SavePaymentMethodRequest,
)
from src.payments.models import PaymentMethod
from src.payments.provider import PaymentProvider


def _to_dto(method: PaymentMethod) -> PaymentMethodDTO:
    return PaymentMethodDTO(
        id=method.id,
        provider=method.provider,
        brand=method.brand,
        last4=method.last4,
        exp_month=method.exp_month,
        exp_year=method.exp_year,
        is_default=method.is_default,
        created_at=method.created_at,
    )


async def save_method(
    db: AsyncSession,
    provider: PaymentProvider,
    user_id: uuid.UUID,
    data: SavePaymentMethodRequest,
) -> PaymentMethodDTO:
    """Exchange the provider intent token for a saved method row.

    If ``is_default`` is set, the caller's existing default is cleared first so the invariant
    holds. The very first saved method becomes default automatically.
    """
    saved = await provider.save_method(str(user_id), data.intent_token)
    make_default = data.is_default
    if not make_default:
        # If the user has no methods yet, this becomes default.
        existing = await db.scalar(
            select(PaymentMethod.id).where(PaymentMethod.user_id == user_id).limit(1)
        )
        make_default = existing is None
    if make_default:
        await _clear_default(db, user_id)
    method = PaymentMethod(
        user_id=user_id,
        provider=provider.name,
        provider_customer_id=saved.provider_customer_id,
        provider_method_token=saved.provider_method_token,
        brand=saved.brand,
        last4=saved.last4,
        exp_month=saved.exp_month,
        exp_year=saved.exp_year,
        is_default=make_default,
    )
    db.add(method)
    await db.flush()
    await db.refresh(method)
    return _to_dto(method)


async def list_methods(db: AsyncSession, user_id: uuid.UUID) -> PaymentMethodListDTO:
    """Caller's saved methods, default first then newest."""
    rows = (
        (
            await db.execute(
                select(PaymentMethod)
                .where(PaymentMethod.user_id == user_id)
                .order_by(PaymentMethod.is_default.desc(), PaymentMethod.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    items = [_to_dto(m) for m in rows]
    return PaymentMethodListDTO(items=items, total=len(items))


async def delete_method(
    db: AsyncSession,
    provider: PaymentProvider,
    user_id: uuid.UUID,
    method_id: uuid.UUID,
) -> None:
    """Detach at the provider and drop the row. 404 if not the caller's method.

    If the deleted card was the default, the next-most-recent method (if any) is promoted.
    """
    method = await _require_owned(db, user_id, method_id)
    was_default = method.is_default
    await provider.delete_method(method.provider_method_token)
    await db.delete(method)
    await db.flush()
    if was_default:
        candidate = await db.scalar(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user_id)
            .order_by(PaymentMethod.created_at.desc())
            .limit(1)
        )
        if candidate is not None:
            candidate.is_default = True
            await db.flush()


async def set_default(
    db: AsyncSession, user_id: uuid.UUID, method_id: uuid.UUID
) -> PaymentMethodDTO:
    """Make ``method_id`` the caller's default (and unset any other)."""
    method = await _require_owned(db, user_id, method_id)
    await _clear_default(db, user_id)
    method.is_default = True
    await db.flush()
    await db.refresh(method)
    return _to_dto(method)


async def get_method(db: AsyncSession, user_id: uuid.UUID, method_id: uuid.UUID) -> PaymentMethod:
    """Return the ORM row for a caller-owned method (used by subscription billing)."""
    return await _require_owned(db, user_id, method_id)


async def get_default_method(db: AsyncSession, user_id: uuid.UUID) -> PaymentMethod | None:
    """The user's default method, if any (used as a fallback by subscription /pay)."""
    result: PaymentMethod | None = await db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.user_id == user_id, PaymentMethod.is_default.is_(True)
        )
    )
    return result


async def _require_owned(
    db: AsyncSession, user_id: uuid.UUID, method_id: uuid.UUID
) -> PaymentMethod:
    method = await db.scalar(
        select(PaymentMethod).where(PaymentMethod.id == method_id, PaymentMethod.user_id == user_id)
    )
    if method is None:
        raise PaymentMethodNotFoundError(str(method_id))
    return method


async def _clear_default(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(PaymentMethod)
        .where(PaymentMethod.user_id == user_id, PaymentMethod.is_default.is_(True))
        .values(is_default=False)
    )
