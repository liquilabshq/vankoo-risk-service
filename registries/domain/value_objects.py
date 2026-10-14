"""Value objects of the Registries bounded context."""
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from shared.domain.exceptions import DomainError


class RegistrySource(StrEnum):
    """A SUNAT registry this service keeps a copy of."""

    TAXPAYERS = "sunat-padron-reducido"
    WITHHOLDING_AGENTS = "sunat-agentes-igv"


class AgentType(StrEnum):
    """The roles SUNAT gives a taxpayer in collecting IGV for it.

    SUNAT designates large, reliable taxpayers as agents, so being one is a
    strong sign of a payer that pays.
    """

    WITHHOLDING = "WITHHOLDING"
    PERCEPTION_DOMESTIC_SALES = "PERCEPTION_DOMESTIC_SALES"
    PERCEPTION_FUEL = "PERCEPTION_FUEL"


@dataclass(frozen=True, slots=True)
class TaxpayerRecord:
    """One row of the padrón reducido del RUC, as this service keeps it.

    Attributes:
        ruc (str): Eleven digits.
        name (str): Name or company name as SUNAT registers it.
        status (str): Taxpayer status (``ACTIVO``, ``BAJA DE OFICIO``…), cut
            by SUNAT to 20 characters.
        domicile_condition (str): Fiscal address condition (``HABIDO``,
            ``NO HABIDO``, ``NO HALLADO…``), cut by SUNAT to 20 characters.
        ubigeo (str | None): The district's six-digit code, if SUNAT gives one.
    """

    ruc: str
    name: str
    status: str
    domicile_condition: str
    ubigeo: str | None

    def __post_init__(self) -> None:
        """Reject a RUC that is not eleven digits.

        Raises:
            DomainError: If the RUC is not exactly eleven digits.
        """
        if len(self.ruc) != 11 or not self.ruc.isdigit():
            raise DomainError(f"'{self.ruc}' is not a RUC")


@dataclass(frozen=True, slots=True)
class AgentRecord:
    """One row of the registry of IGV withholding and perception agents.

    Attributes:
        ruc (str): Eleven digits.
        agent_type (AgentType): Which role SUNAT gave it.
        since (date | None): When the role started.
        resolution (str | None): The SUNAT resolution that designated it.
    """

    ruc: str
    agent_type: AgentType
    since: date | None
    resolution: str | None

    def __post_init__(self) -> None:
        """Reject a RUC that is not eleven digits.

        Raises:
            DomainError: If the RUC is not exactly eleven digits.
        """
        if len(self.ruc) != 11 or not self.ruc.isdigit():
            raise DomainError(f"'{self.ruc}' is not a RUC")
