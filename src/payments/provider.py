"""Provider-agnostic payment interface and a deterministic ``FakeProvider`` for dev/test.

The real provider client (Stripe / PayPal / etc.) is not chosen yet — the rest of the codebase
talks only to this interface, so swapping it in is a pure substitution.

``FakeProvider`` is the default in every environment until the real one lands. It accepts a
shared "secret" for callback verification (configured via ``settings.payment_provider_secret``)
and returns deterministic transaction ids of the form ``fake-<uuid4>``.
"""

import hmac
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated

from fastapi import Depends

from src.api.core.configs import settings


@dataclass(frozen=True, slots=True)
class ChargeRequest:
    """Domain-side description of a charge to be created with the provider."""

    amount: Decimal
    currency: str
    reference: str  # Our ``OrderPayment.id``, used as the idempotency / lookup key.
    customer_id: str | None = None  # External provider customer id (saved-method, future).


@dataclass(frozen=True, slots=True)
class ChargeResult:
    """The provider's response to a charge call: transaction id + outcome."""

    transaction_id: str
    status: str  # "completed" | "failed"


@dataclass(frozen=True, slots=True)
class RefundResult:
    """The provider's response to a refund call."""

    status: str  # "refunded" | "failed"


class PaymentProvider(ABC):
    """Minimal surface a payment gateway must expose for orders + subscriptions."""

    name: str

    @abstractmethod
    async def create_charge(self, charge: ChargeRequest) -> ChargeResult:
        """Initiate a charge; may settle synchronously or asynchronously via a callback."""

    @abstractmethod
    async def refund(self, provider_transaction_id: str) -> RefundResult:
        """Refund a previously completed transaction (provider may charge a fee)."""

    @abstractmethod
    def verify_callback(self, payload: bytes, signature: str | None) -> bool:
        """Authenticate a webhook payload; return ``True`` iff the signature matches."""


class FakeProvider(PaymentProvider):
    """Deterministic in-process provider used in dev/tests until a real one is chosen.

    The charge result is driven by the request's ``reference`` prefix so tests can exercise
    both paths:

    - ``reference`` starts with ``fail-`` → ``status="failed"``.
    - otherwise → ``status="completed"``.

    Callback signature is a constant-time compare against ``settings.payment_provider_secret``.
    """

    name = "fake"

    async def create_charge(self, charge: ChargeRequest) -> ChargeResult:
        outcome = "failed" if charge.reference.startswith("fail-") else "completed"
        return ChargeResult(transaction_id=f"fake-{uuid.uuid4()}", status=outcome)

    async def refund(self, provider_transaction_id: str) -> RefundResult:
        return RefundResult(status="refunded")

    def verify_callback(self, payload: bytes, signature: str | None) -> bool:
        expected = settings.payment_provider_secret
        if not expected or not signature:
            return False
        return hmac.compare_digest(signature, expected)


def get_payment_provider() -> PaymentProvider:
    """FastAPI dependency: returns the active payment provider (FakeProvider until selected)."""
    return FakeProvider()


PaymentProviderDep = Annotated[PaymentProvider, Depends(get_payment_provider)]
