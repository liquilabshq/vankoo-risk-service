"""What other bounded contexts may ask the Registries context.

Primitives in, primitives out: the caller never sees this context's model,
so the registries can change their tables without breaking the assessments.
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from registries.domain.value_objects import RegistrySource
from registries.infrastructure.repositories import (
    SqlAlchemyRegistrySnapshotRepository,
    SqlAlchemyTaxpayerRepository,
    SqlAlchemyWithholdingAgentRepository,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PayerStandingRecord:
    """What SUNAT's registries say about a RUC.

    Attributes:
        registry_loaded (bool): Whether the padrón was ever loaded; if not, every
            other field is empty and says nothing about the RUC.
        found (bool): Whether the RUC is in the padrón.
        name (str | None): Its registered name.
        status (str | None): Its taxpayer status, e.g. ``ACTIVO``.
        domicile_condition (str | None): Its address condition, e.g. ``HABIDO``.
        ubigeo (str | None): Its district code.
        agent_types (tuple[str, ...]): Its IGV agent roles, e.g. ``("WITHHOLDING",)``.
    """

    registry_loaded: bool
    found: bool
    name: str | None = None
    status: str | None = None
    domicile_condition: str | None = None
    ubigeo: str | None = None
    agent_types: tuple[str, ...] = ()


class RegistriesContextFacade:
    """What other bounded contexts may ask the Registries context."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the facade on the caller's session.

        Args:
            session (AsyncSession): The caller's session, so the answer belongs to its transaction.
        """
        self._taxpayers = SqlAlchemyTaxpayerRepository(session)
        self._agents = SqlAlchemyWithholdingAgentRepository(session)
        self._snapshots = SqlAlchemyRegistrySnapshotRepository(session)

    async def payer_standing(self, ruc: str) -> PayerStandingRecord:
        """Tell what SUNAT's registries say about a RUC.

        Args:
            ruc (str): Eleven digits.

        Returns:
            PayerStandingRecord: The standing; ``registry_loaded`` is false while
            the padrón has never been loaded.
        """
        if await self._snapshots.find_latest(RegistrySource.TAXPAYERS) is None:
            return PayerStandingRecord(registry_loaded=False, found=False)
        taxpayer = await self._taxpayers.find_by_ruc(ruc)
        agent_types = tuple(agent.value for agent in await self._agents.find_types_by_ruc(ruc))
        if taxpayer is None:
            return PayerStandingRecord(registry_loaded=True, found=False, agent_types=agent_types)
        return PayerStandingRecord(
            registry_loaded=True,
            found=True,
            name=taxpayer.name,
            status=taxpayer.status,
            domicile_condition=taxpayer.domicile_condition,
            ubigeo=taxpayer.ubigeo,
            agent_types=agent_types,
        )
