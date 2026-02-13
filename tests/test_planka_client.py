import pytest
import respx
from httpx import Response

from app.integrations.planka_client import PlankaAuthError, PlankaClient


@pytest.mark.asyncio
async def test_list_boards_success() -> None:
    client = PlankaClient(
        base_url="https://planka.example.com",
        username_or_email="user",
        password="pass",
    )
    with respx.mock(base_url="https://planka.example.com") as router:
        router.post("/api/access-tokens").mock(
            return_value=Response(200, json={"item": "token"})
        )
        router.get("/api/boards").mock(
            return_value=Response(200, json=[{"id": "1", "name": "Demo"}])
        )
        await client.start()
        try:
            boards = await client.list_boards()
            assert boards == [{"id": "1", "name": "Demo"}]
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_list_boards_auth_error() -> None:
    client = PlankaClient(
        base_url="https://planka.example.com",
        username_or_email="user",
        password="pass",
    )
    with respx.mock(base_url="https://planka.example.com") as router:
        router.post("/api/access-tokens").mock(
            return_value=Response(200, json={"item": "token"})
        )
        router.get("/api/boards").mock(return_value=Response(401, json={"error": "nope"}))
        # The fallback to /api/projects also returns 401.
        router.get("/api/projects").mock(return_value=Response(401, json={"error": "nope"}))
        await client.start()
        try:
            with pytest.raises(PlankaAuthError):
                await client.list_boards()
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_login_auth_error() -> None:
    client = PlankaClient(
        base_url="https://planka.example.com",
        username_or_email="user",
        password="wrong",
    )
    with respx.mock(base_url="https://planka.example.com") as router:
        router.post("/api/access-tokens").mock(return_value=Response(401))
        with pytest.raises(PlankaAuthError):
            await client.start()
