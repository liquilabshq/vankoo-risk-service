"""ORM models of the Registries bounded context.

``taxpayers`` and ``withholding_agents`` are replaced whole on every refresh
(see ``bulk.py``): they are a copy of SUNAT's files, never edited row by row,
so they carry no audit columns.
"""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models import Base


class TaxpayerModel(Base):
    """The ``taxpayers`` table: the padrón reducido del RUC, one row per RUC."""

    __tablename__ = "taxpayers"

    ruc: Mapped[str] = mapped_column(String(11), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    domicile_condition: Mapped[str] = mapped_column(String(40))
    ubigeo: Mapped[str | None] = mapped_column(String(6))


class WithholdingAgentModel(Base):
    """The ``withholding_agents`` table: one row per RUC and agent role."""

    __tablename__ = "withholding_agents"

    ruc: Mapped[str] = mapped_column(String(11), primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    since: Mapped[date | None] = mapped_column(Date)
    resolution: Mapped[str | None] = mapped_column(String(120))


class RegistrySnapshotModel(Base):
    """The ``registry_snapshots`` table: one row per successful load."""

    __tablename__ = "registry_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(120))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rows_loaded: Mapped[int] = mapped_column(BigInteger)
    rows_rejected: Mapped[int] = mapped_column(BigInteger)
