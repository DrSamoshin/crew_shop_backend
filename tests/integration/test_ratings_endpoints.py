"""Integration tests for the rating API and catalog user-rating enrichment."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.catalog.models import Product, ProductCategory, ProductType
from src.orders.enums import OrderStatus, OrderType
from src.orders.models import Order, OrderProduct
from src.users.models import User
from tests.integration.crew_auth_stub import mint_access_token

Maker = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class Env:
    user_id: uuid.UUID
    product_id: uuid.UUID
    other_product_id: uuid.UUID
    token: str


async def _setup(maker: Maker, *, order_status: str = OrderStatus.COMPLETED.value) -> Env:
    """Seed a user + two products; the first is referenced by an order of ``order_status``."""
    async with maker() as s:
        user = User(display_name="Rater", auth_user_id=uuid.uuid4())
        product_type = ProductType(name=f"t-{uuid.uuid4()}")
        category = ProductCategory(name=f"c-{uuid.uuid4()}", product_type=product_type)
        s.add_all([user, category, product_type])
        await s.flush()

        product = Product(
            name="Ethiopia",
            product_category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("12.50"),
        )
        other = Product(
            name="Brewer",
            product_category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("20.00"),
        )
        s.add_all([product, other])
        await s.flush()

        order = Order(
            user_id=user.id,
            order_type=OrderType.PICKUP.value,
            total_price=Decimal("12.50"),
            status=order_status,
        )
        order.products = [
            OrderProduct(
                product_id=product.id,
                product_name=product.name,
                product_price=product.price,
                quantity=1,
            )
        ]
        s.add(order)
        await s.flush()

        access = mint_access_token(user.auth_user_id)
        await s.commit()
        return Env(user.id, product.id, other.id, access)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------- write


async def test_rate_product_upserts_and_recomputes(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    first = await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 5}, headers=_auth(env.token)
    )
    assert first.status_code == 200
    body = first.json()
    assert body["user_rating"] == 5
    assert body["average_rating"] == "5.0"
    assert body["total_ratings"] == 1
    assert body["rating_distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1}

    update = await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 3}, headers=_auth(env.token)
    )
    assert update.status_code == 200
    body = update.json()
    assert body["user_rating"] == 3
    assert body["total_ratings"] == 1  # still one rating, just updated
    assert body["average_rating"] == "3.0"


async def test_rate_without_purchase_403(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.put(
        f"/v1/products/{env.other_product_id}/rating",  # no order for this product
        json={"rating": 4},
        headers=_auth(env.token),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "RATING_NOT_PURCHASED"


async def test_cancelled_order_does_not_grant_rating(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker, order_status=OrderStatus.CANCELLED.value)

    resp = await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 5}, headers=_auth(env.token)
    )
    assert resp.status_code == 403


async def test_rate_value_out_of_range_400(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 10}, headers=_auth(env.token)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "RATING_INVALID_VALUE"


async def test_rate_requires_auth(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.put(f"/v1/products/{env.product_id}/rating", json={"rating": 5})
    assert resp.status_code == 401


async def test_rate_unknown_product_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.put(
        f"/v1/products/{uuid.uuid4()}/rating", json={"rating": 4}, headers=_auth(env.token)
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "PRODUCT_NOT_FOUND"


# --------------------------------------------------------------------- delete


async def test_delete_rating_recomputes(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 4}, headers=_auth(env.token)
    )

    resp = await client.delete(f"/v1/products/{env.product_id}/rating", headers=_auth(env.token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_rating"] is None
    assert body["total_ratings"] == 0
    assert body["average_rating"] is None


async def test_delete_missing_rating_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.delete(f"/v1/products/{env.product_id}/rating", headers=_auth(env.token))
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "RATING_NOT_FOUND"


# ----------------------------------------------------------------- breakdown


async def test_breakdown_public(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 5}, headers=_auth(env.token)
    )

    resp = await client.get(f"/v1/products/{env.product_id}/rating")  # no auth
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_ratings"] == 1
    assert body["average_rating"] == "5.0"
    assert body["rating_distribution"]["5"] == {"count": 1, "percentage": 100.0}
    assert body["rating_distribution"]["1"] == {"count": 0, "percentage": 0.0}


async def test_breakdown_unknown_product_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.get(f"/v1/products/{uuid.uuid4()}/rating")
    assert resp.status_code == 404


# ----------------------------------------------------------------- my ratings


async def test_list_my_ratings(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 4}, headers=_auth(env.token)
    )

    resp = await client.get("/v1/users/me/ratings", headers=_auth(env.token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["product_name"] == "Ethiopia"
    assert body["items"][0]["rating"] == 4


# ------------------------------------------------------------- catalog enrichment


async def test_catalog_carries_user_rating_and_can_rate(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup(maker)
    await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 5}, headers=_auth(env.token)
    )

    listed = await client.get("/v1/catalog/products?limit=50", headers=_auth(env.token))
    assert listed.status_code == 200
    items = {item["id"]: item for item in listed.json()["items"]}
    purchased = items[str(env.product_id)]
    other = items[str(env.other_product_id)]
    assert purchased["user_rating"] == 5
    assert purchased["can_rate"] is True
    assert other["user_rating"] is None
    assert other["can_rate"] is False

    detail = await client.get(f"/v1/catalog/products/{env.product_id}", headers=_auth(env.token))
    assert detail.status_code == 200
    assert detail.json()["user_rating"] == 5
    assert detail.json()["can_rate"] is True


async def test_catalog_anonymous_fields_null(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    await client.put(
        f"/v1/products/{env.product_id}/rating", json={"rating": 4}, headers=_auth(env.token)
    )

    listed = await client.get("/v1/catalog/products?limit=50")  # anonymous
    items = {item["id"]: item for item in listed.json()["items"]}
    assert items[str(env.product_id)]["user_rating"] is None
    assert items[str(env.product_id)]["can_rate"] is False
