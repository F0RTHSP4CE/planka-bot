from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PlankaClientError(Exception):
    """Base exception raised for Planka API related failures."""


class PlankaAuthError(PlankaClientError):
    """Raised when Planka rejects authentication."""


class PlankaClient:
    def __init__(
        self,
        base_url: str,
        username_or_email: str,
        password: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username_or_email = username_or_email
        self._password = password
        self._timeout_seconds = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        token = await self._login()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=httpx.Timeout(self._timeout_seconds),
        )

    async def _login(self) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_seconds)) as client:
            response = await client.post(
                f"{self._base_url}/api/access-tokens",
                json={
                    "emailOrUsername": self._username_or_email,
                    "password": self._password,
                },
            )
        if response.status_code in {401, 403}:
            raise PlankaAuthError("Planka login failed: invalid credentials")
        if response.is_error:
            raise PlankaClientError(
                f"Planka login failed: {response.status_code} {response.text[:200]}"
            ) from None
        data = response.json()
        token = data.get("item")
        if not token:
            raise PlankaAuthError("Planka login failed: no token returned")
        return token

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> dict[str, Any]:
        return await self._get_json("/api/users/me")

    async def list_boards(self) -> list[dict[str, Any]]:
        try:
            payload = await self._get_json("/api/boards")
            items = _extract_items(payload)
            if items is not None:
                return items
        except PlankaClientError:
            # Some Planka deployments do not expose /api/boards as JSON.
            pass

        projects_payload = await self._get_json("/api/projects")
        if not isinstance(projects_payload, dict):
            return []
        included = projects_payload.get("included")
        if not isinstance(included, dict):
            return []
        boards = included.get("boards")
        if not isinstance(boards, list):
            return []
        return [board for board in boards if isinstance(board, dict)]

    async def create_card(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        card_type: str = "task",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "type": card_type,
            # Position 0 = top of list; 65535 = end.
            "position": 0.0,
        }
        if description:
            payload["description"] = description
        data = await self._post_json(f"/api/lists/{list_id}/cards", payload=payload)
        return _extract_item(data)

    async def get_list(self, list_id: str) -> dict[str, Any] | None:
        """Fetch list details (may include boardId)."""
        try:
            payload = await self._get_json(f"/api/lists/{list_id}")
            if isinstance(payload, dict):
                return payload.get("item") or payload
            return None
        except PlankaClientError:
            return None

    async def get_cards(self, list_id: str) -> list[dict[str, Any]]:
        payload = await self._get_json(f"/api/lists/{list_id}/cards")
        items = _extract_items(payload)
        if items is not None:
            return items
        return []

    async def get_card(self, card_id: str) -> dict[str, Any] | None:
        """Fetch single card with full details (name, description, task lists, tasks, attachments).

        Returns the full API response: {item: card, included: {taskLists, tasks, attachments, ...}}.
        Planka has no separate GET for task-lists or attachments; they come from card show.
        """
        try:
            payload = await self._get_json(f"/api/cards/{card_id}")
            if isinstance(payload, dict):
                return payload
            return None
        except PlankaClientError:
            return None

    async def download_attachment(self, attachment_id: str) -> bytes | None:
        """Download attachment file bytes (for images)."""
        try:
            client = self._require_client()
            response = await client.get(f"/api/attachments/{attachment_id}/file")
            if response.is_error:
                return None
            return response.content
        except httpx.HTTPError:
            return None

    async def move_card(
        self,
        card_id: str,
        list_id: str,
        *,
        position: float | None = None,
    ) -> dict[str, Any]:
        pos = position if position is not None else 65535.0
        data = await self._patch_json(
            f"/api/cards/{card_id}",
            payload={
                "listId": list_id,
                "position": pos,
            },
        )
        return _extract_item(data)

    async def create_task_list(
        self,
        card_id: str,
        name: str = "Checklist",
    ) -> dict[str, Any]:
        data = await self._post_json(
            f"/api/cards/{card_id}/task-lists",
            payload={
                "name": name,
                "position": 65536.0,
                "showOnFrontOfCard": True,
            },
        )
        return _extract_item(data)

    async def create_task(
        self,
        task_list_id: str,
        name: str,
        position: float,
    ) -> dict[str, Any]:
        data = await self._post_json(
            f"/api/task-lists/{task_list_id}/tasks",
            payload={
                "name": name,
                "position": position,
            },
        )
        return _extract_item(data)

    async def get_board_actions(
        self,
        board_id: str,
        before_id: str | None = None,
    ) -> dict[str, Any]:
        path = f"/api/boards/{board_id}/actions"
        if before_id:
            path = f"{path}?beforeId={before_id}"
        return await self._get_json(path)

    async def create_attachment(
        self,
        card_id: str,
        file_name: str,
        file_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        return await self._post_multipart(
            f"/api/cards/{card_id}/attachments",
            data={"type": "file", "name": file_name},
            files={"file": (file_name, file_bytes, content_type)},
        )

    async def _get_json(self, path: str) -> Any:
        return await self._request_json("GET", path)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        return await self._request_json("POST", path, payload=payload)

    async def _patch_json(self, path: str, payload: dict[str, Any]) -> Any:
        return await self._request_json("PATCH", path, payload=payload)

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        client = self._require_client()
        try:
            response = await client.request(method, path, json=payload)
        except httpx.TimeoutException as exc:
            raise PlankaClientError("Planka API timed out") from exc
        except httpx.HTTPError as exc:
            raise PlankaClientError("Planka API request failed") from exc

        return self._handle_response(response)

    async def _post_multipart(
        self,
        path: str,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> Any:
        client = self._require_client()
        try:
            response = await client.post(path, data=data, files=files)
        except httpx.TimeoutException as exc:
            raise PlankaClientError("Planka API timed out") from exc
        except httpx.HTTPError as exc:
            raise PlankaClientError("Planka API request failed") from exc

        return self._handle_response(response)

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if response.status_code == 401:
            raise PlankaAuthError("Planka authentication failed")
        if response.status_code == 403:
            raise PlankaClientError(f"Planka API forbidden: {response.text[:200]}")
        if response.is_error:
            raise PlankaClientError(
                f"Planka API returned {response.status_code}: {response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            url = getattr(response.request, "url", None) or "?"
            content_type = response.headers.get("content-type", "unknown")
            body_preview = response.text[:500] if response.text else "(empty)"
            logger.warning(
                "Planka API returned invalid JSON: url=%s status=%s content_type=%s body_preview=%r",
                url,
                response.status_code,
                content_type,
                body_preview,
            )
            raise PlankaClientError("Planka API returned invalid JSON") from exc

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PlankaClient was used before initialization")
        return self._client


def _extract_items(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        if isinstance(payload.get("item"), list):
            return [item for item in payload["item"] if isinstance(item, dict)]

    return None


def _extract_item(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        nested_item = payload.get("item")
        if isinstance(nested_item, dict):
            return nested_item
        return payload
    raise PlankaClientError("Planka API returned an unexpected response payload")
