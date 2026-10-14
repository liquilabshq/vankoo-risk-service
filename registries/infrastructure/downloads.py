"""HTTP adapter that finds and downloads SUNAT's registries.

The version of a file is its ``Last-Modified`` header: SUNAT rebuilds the
padrón every night, and comparing headers costs one ``HEAD`` instead of a
400 MB download. The agents registry is published once a month under a name
with the period (``…_202609.zip``), so finding it means trying the current
month and going back until one exists.
"""
import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx

from registries.application.outbound_services import PublishedVersion, RegistryDownloader, RegistryUnavailableError
from registries.domain.value_objects import RegistrySource
from registries.infrastructure.settings import RegistrySettings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024


class HttpRegistryDownloader(RegistryDownloader):
    """Asks SUNAT and the open-data portal for their files over HTTP."""

    def __init__(self, client: httpx.AsyncClient, settings: RegistrySettings, today: Callable[[], date]) -> None:
        """Initialize the downloader.

        Args:
            client (httpx.AsyncClient): A client that follows redirects and sends
                ``settings.user_agent``.
            settings (RegistrySettings): Where the files are.
            today (Callable[[], date]): Today's date, to name the agents file's period.
        """
        self._client = client
        self._settings = settings
        self._today = today

    async def find_published_version(self, source: RegistrySource) -> PublishedVersion:
        if source is RegistrySource.TAXPAYERS:
            url = self._settings.taxpayers_url
            response = await self._head(url)
            if response.status_code != httpx.codes.OK:
                raise RegistryUnavailableError(f"{url} answered HTTP {response.status_code}")
            return PublishedVersion(source=source, version=self._version_of(response), url=url)

        for period in self._recent_periods():
            url = self._settings.agents_url_template.format(period=period)
            response = await self._head(url)
            if response.status_code == httpx.codes.OK:
                return PublishedVersion(source=source, version=f"{period} {self._version_of(response)}", url=url)
        raise RegistryUnavailableError(
            f"No agents registry published in the last {self._settings.agents_months_back} months"
        )

    async def download(self, published: PublishedVersion, directory: Path) -> Path:
        target = directory / published.url.rsplit("/", 1)[-1]
        try:
            async with self._client.stream("GET", published.url) as response:
                if response.status_code != httpx.codes.OK:
                    raise RegistryUnavailableError(f"{published.url} answered HTTP {response.status_code}")
                with target.open("wb") as file:
                    async for chunk in response.aiter_bytes(CHUNK_SIZE):
                        file.write(chunk)
        except httpx.HTTPError as error:
            raise RegistryUnavailableError(f"Downloading {published.url} failed: {error}") from error
        logger.info("Downloaded %s (%d bytes)", target.name, target.stat().st_size)
        return target

    async def _head(self, url: str) -> httpx.Response:
        try:
            return await self._client.head(url)
        except httpx.HTTPError as error:
            raise RegistryUnavailableError(f"{url} could not be reached: {error}") from error

    def _recent_periods(self) -> list[str]:
        today = self._today()
        year, month = today.year, today.month
        periods = []
        for _ in range(self._settings.agents_months_back + 1):
            periods.append(f"{year:04d}{month:02d}")
            year, month = (year, month - 1) if month > 1 else (year - 1, 12)
        return periods

    @staticmethod
    def _version_of(response: httpx.Response) -> str:
        return (
            response.headers.get("last-modified")
            or response.headers.get("etag")
            or f"size {response.headers.get('content-length', 'unknown')}"
        )
