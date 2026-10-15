"""What the Assessments context asks the Registries context.

The only module of Assessments that imports Registries: it asks the
registries' facade with primitives and answers in Assessments' own terms.
"""
from assessments.domain.value_objects import PayerStanding, Ruc, SanctionPeriod
from registries.interfaces.acl import RegistriesContextFacade, SanctionPeriodRecord

WITHHOLDING = "WITHHOLDING"
PERCEPTION_ROLES = frozenset({"PERCEPTION_DOMESTIC_SALES", "PERCEPTION_FUEL"})


class ExternalRegistriesService:
    """What Assessments needs to know about a payer from the public registries."""

    def __init__(self, registries_facade: RegistriesContextFacade) -> None:
        """Initialize the service on the registries' facade.

        Args:
            registries_facade (RegistriesContextFacade): Answers on the caller's session.
        """
        self._registries = registries_facade

    async def payer_standing(self, ruc: Ruc) -> PayerStanding:
        """Tell what the public registries say about the payer of an invoice."""
        record = await self._registries.payer_standing(ruc.value)
        return PayerStanding(
            registry_loaded=record.registry_loaded,
            found=record.found,
            name=record.name,
            status=record.status,
            domicile_condition=record.domicile_condition,
            ubigeo=record.ubigeo,
            withholding_agent=WITHHOLDING in record.agent_types,
            perception_agent=bool(PERCEPTION_ROLES.intersection(record.agent_types)),
            shell_company=record.shell_company,
            coactive_debt=record.coactive_debt,
            oece_disqualifications=_periods(record.oece_disqualifications),
            oece_fines=_periods(record.oece_fines),
            environmental_infractions=record.environmental_infractions,
            unavailable_sources=record.unavailable_sources,
        )


def _periods(records: tuple[SanctionPeriodRecord, ...]) -> tuple[SanctionPeriod, ...]:
    return tuple(SanctionPeriod(record.starts_on, record.ends_on, record.amount) for record in records)
