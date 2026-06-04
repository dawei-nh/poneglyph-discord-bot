from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable, Mapping
from typing import Any, cast
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from optcg_card_bot.errors import (
    NoSearchResultsError,
    PoneglyphNetworkError,
    PoneglyphNotFoundError,
    PoneglyphRateLimitError,
    PoneglyphServerError,
    PoneglyphValidationError,
)
from optcg_card_bot.models import (
    CardDetail,
    CardDetailResponse,
    RandomCardResponse,
    SearchResponse,
)

TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
QueryParams = Mapping[str, str | int | float | bool | None]


class PoneglyphClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.poneglyph.one",
        api_prefix: str = "/v1",
        timeout: float = 10.0,
        min_interval: float = 0.25,
        max_retries: int = 2,
        user_agent: str = "poneglyph-discord-bot/0.1.0",
    ) -> None:
        self._owned_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": user_agent,
            },
        )
        self._api_prefix = "/" + api_prefix.strip("/")
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_request_at = 0.0
        self._pace_lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owned_client:
            await self._http.aclose()

    async def search_cards(
        self,
        query: str | None,
        *,
        page: int = 1,
        limit: int = 60,
        sort: str | None = None,
        order: str | None = None,
        collapse: str = "card",
        lang: str = "en",
    ) -> SearchResponse:
        params: dict[str, str | int] = {
            "page": page,
            "limit": limit,
            "collapse": collapse,
            "lang": lang,
        }
        if query:
            params["q"] = query
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order

        payload = await self._request_json("GET", "/search", params=params)
        try:
            return SearchResponse.model_validate(payload)
        except ValidationError as exc:
            raise PoneglyphServerError from exc

    async def get_card(self, card_number: str, *, lang: str = "en") -> CardDetail:
        encoded_card_number = quote(card_number.upper(), safe="")
        payload = await self._request_json(
            "GET",
            f"/cards/{encoded_card_number}",
            params={"lang": lang},
        )
        try:
            return CardDetailResponse.model_validate(payload).data
        except ValidationError as exc:
            raise PoneglyphServerError from exc

    async def get_random(
        self,
        *,
        lang: str = "en",
        set: str | None = None,
        color: str | None = None,
        type: str | None = None,
        rarity: str | None = None,
    ) -> CardDetail:
        params = {
            key: value
            for key, value in {
                "lang": lang,
                "set": set,
                "color": color,
                "type": type,
                "rarity": rarity,
            }.items()
            if value is not None
        }
        payload = await self._request_json("GET", "/random", params=params)
        try:
            return RandomCardResponse.model_validate(payload).data
        except ValidationError as exc:
            raise PoneglyphServerError from exc

    async def get_random_from_query(
        self,
        query: str,
        *,
        lang: str = "en",
        random_page: Callable[[int], int] | None = None,
    ) -> CardDetail:
        first_page = await self.search_cards(query, page=1, limit=1, lang=lang)
        total = first_page.pagination.total
        if total <= 0:
            raise NoSearchResultsError

        page = (
            random_page(total)
            if random_page is not None
            else random.randint(1, total)
        )
        selected_page = await self.search_cards(query, page=page, limit=1, lang=lang)
        if not selected_page.data:
            raise NoSearchResultsError

        return await self.get_card(selected_page.data[0].card_number, lang=lang)

    async def _request_json(
        self,
        method: str,
        path: str,
        params: QueryParams | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_path = f"{self._api_prefix}{path}"
        response: httpx.Response | None = None

        for attempt in range(self._max_retries + 1):
            try:
                await self._pace()
                response = await self._http.request(
                    method,
                    request_path,
                    params=params,
                    json=json_body,
                )
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    await self._sleep_for_retry(None, attempt)
                    continue
                raise PoneglyphNetworkError from exc

            if (
                response.status_code in TRANSIENT_STATUSES
                and attempt < self._max_retries
            ):
                await self._sleep_for_retry(response, attempt)
                continue

            self._raise_for_status(response)
            try:
                payload: Any = response.json()
            except ValueError as exc:
                raise PoneglyphServerError from exc

            if not isinstance(payload, dict):
                raise PoneglyphServerError
            return cast("dict[str, Any]", payload)

        if response is not None:
            self._raise_for_status(response)
        raise PoneglyphNetworkError

    async def _pace(self) -> None:
        if self._min_interval <= 0:
            return

        async with self._pace_lock:
            now = time.monotonic()
            wait_seconds = self._last_request_at + self._min_interval - now
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_at = time.monotonic()

    async def _sleep_for_retry(
        self,
        response: httpx.Response | None,
        attempt: int,
    ) -> None:
        retry_after = response.headers.get("Retry-After") if response else None
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 0.25 * (attempt + 1)
            else:
                delay = max(delay, 0)
        else:
            delay = 0.25 * (attempt + 1)
        await asyncio.sleep(delay)

    def _raise_for_status(self, response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return
        if status_code == 400:
            raise PoneglyphValidationError
        if status_code == 404:
            raise PoneglyphNotFoundError
        if status_code == 429:
            raise PoneglyphRateLimitError
        if status_code >= 500:
            raise PoneglyphServerError
        raise PoneglyphValidationError
