"""Bulk replacement of a registry table, for PostgreSQL.

A refresh writes millions of rows, far too many for the ORM. The file is
streamed into a new table with ``COPY`` (asyncpg's ``copy_records_to_table``),
in batches that pass through a temporary table so that a repeated key is
skipped instead of failing the whole load. When every row is in, the new table
replaces the old one: drop, rename, rename its primary key. All of it runs in
the caller's transaction, so readers see the old copy until the commit, and a
failure leaves the old copy untouched.
"""
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from registries.application.outbound_services import LoadResult, RegistryWriter
from registries.domain.value_objects import AgentRecord, RegistrySource, TaxpayerRecord
from registries.infrastructure.parsers import read_agents, read_taxpayers

logger = logging.getLogger(__name__)

BATCH_SIZE = 50_000
PROGRESS_EVERY = 1_000_000


@dataclass(frozen=True, slots=True)
class _TableSpec:
    name: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]


TAXPAYERS = _TableSpec("taxpayers", ("ruc", "name", "status", "domicile_condition", "ubigeo"), ("ruc",))
WITHHOLDING_AGENTS = _TableSpec(
    "withholding_agents", ("ruc", "agent_type", "since", "resolution"), ("ruc", "agent_type")
)


class PostgresRegistryWriter(RegistryWriter):
    """Replaces a registry table with the rows of a downloaded file."""

    def __init__(self, session: AsyncSession, batch_size: int = BATCH_SIZE) -> None:
        """Initialize the writer on the unit of work's session.

        Args:
            session (AsyncSession): The session whose transaction the load runs in.
            batch_size (int): Rows sent per ``COPY``.
        """
        self._session = session
        self._batch_size = batch_size

    async def replace(self, source: RegistrySource, file: Path) -> LoadResult:
        if source is RegistrySource.TAXPAYERS:
            return await self._replace(TAXPAYERS, (_taxpayer_row(record) for record in read_taxpayers(file)))
        return await self._replace(WITHHOLDING_AGENTS, (_agent_row(record) for record in read_agents(file)))

    async def _replace(self, table: _TableSpec, rows: Iterable[tuple[Any, ...] | None]) -> LoadResult:
        connection = await (await self._session.connection()).get_raw_connection()
        pg: Any = connection.driver_connection
        loading, batch = f"{table.name}_loading", f"{table.name}_batch"
        columns = ", ".join(table.columns)

        await pg.execute(f"DROP TABLE IF EXISTS {loading}")
        await pg.execute(f"CREATE TABLE {loading} (LIKE {table.name} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)")
        primary_key = ", ".join(table.primary_key)
        await pg.execute(f"ALTER TABLE {loading} ADD CONSTRAINT pk_{loading} PRIMARY KEY ({primary_key})")
        await pg.execute(f"CREATE TEMP TABLE {batch} (LIKE {table.name} INCLUDING DEFAULTS) ON COMMIT DROP")

        loaded = rejected = 0
        pending: list[tuple[Any, ...]] = []

        async def flush() -> None:
            nonlocal loaded, rejected
            if not pending:
                return
            await pg.copy_records_to_table(batch, records=pending, columns=table.columns)
            status = await pg.execute(
                f"INSERT INTO {loading} ({columns}) SELECT {columns} FROM {batch} ON CONFLICT DO NOTHING"
            )
            inserted = int(status.rsplit(" ", 1)[-1])
            loaded += inserted
            rejected += len(pending) - inserted
            await pg.execute(f"TRUNCATE {batch}")
            previous = (loaded - inserted) // PROGRESS_EVERY
            if loaded // PROGRESS_EVERY > previous:
                logger.info("%s: %d rows loaded so far", table.name, loaded)
            pending.clear()

        for row in rows:
            if row is None:
                rejected += 1
                continue
            pending.append(row)
            if len(pending) >= self._batch_size:
                await flush()
        await flush()

        await pg.execute(f"DROP TABLE {table.name}")
        await pg.execute(f"ALTER TABLE {loading} RENAME TO {table.name}")
        await pg.execute(f"ALTER TABLE {table.name} RENAME CONSTRAINT pk_{loading} TO pk_{table.name}")
        await pg.execute(f"ANALYZE {table.name}")
        return LoadResult(rows_loaded=loaded, rows_rejected=rejected)


def _taxpayer_row(record: TaxpayerRecord | None) -> tuple[Any, ...] | None:
    if record is None:
        return None
    return (record.ruc, record.name, record.status, record.domicile_condition, record.ubigeo)


def _agent_row(record: AgentRecord | None) -> tuple[Any, ...] | None:
    if record is None:
        return None
    return (record.ruc, record.agent_type.value, record.since, record.resolution)
