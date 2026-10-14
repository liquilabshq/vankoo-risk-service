"""Value objects of the Assessments bounded context.

Each one refuses to exist in a bad state: a RUC that is not eleven digits, a
negative amount or a blank auction reference fails here, as a ``DomainError``,
before any assessment is built from it.
"""
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from shared.domain.exceptions import DomainError

AUCTION_ID_MAX_LENGTH = 64
ASSESSMENT_ID_MAX_LENGTH = 100
ASSESSMENT_ID_PREFIX = "risk-"
PAYER_NAME_MAX_LENGTH = 255


class RiskGrade(StrEnum):
    """The class of risk an assessment gives an auction; A is the safest."""

    A = "A"
    B = "B"
    C = "C"


class DeliveryStatus(StrEnum):
    """Whether Investment has received the assessment.

    ``PENDING`` until Investment answers; ``DELIVERED`` once it accepted the
    grade; ``REJECTED`` when it refused it for good (the auction no longer
    accepts an evaluation, or does not exist).
    """

    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"


class Currency(StrEnum):
    """The currencies an invoice can be issued in."""

    PEN = "PEN"
    USD = "USD"


@dataclass(frozen=True, slots=True)
class AuctionId:
    """Reference to an auction, which lives in the Investment context.

    Attributes:
        value (str): The auction's identifier as Investment assigned it.
    """

    value: str

    def __post_init__(self) -> None:
        """Reject a blank or overlong identifier.

        Raises:
            DomainError: If the value is blank or longer than 64 characters.
        """
        normalized = self.value.strip()
        if not normalized:
            raise DomainError("Auction id must not be blank")
        if len(normalized) > AUCTION_ID_MAX_LENGTH:
            raise DomainError(f"Auction id must be at most {AUCTION_ID_MAX_LENGTH} characters")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class AssessmentId:
    """The public identifier of one assessment, the one Investment stores.

    Attributes:
        value (str): ``risk-`` followed by a UUID, e.g. ``risk-0b6f…``.
    """

    value: str

    def __post_init__(self) -> None:
        """Reject a blank or overlong identifier.

        Raises:
            DomainError: If the value is blank or longer than Investment accepts.
        """
        normalized = self.value.strip()
        if not normalized:
            raise DomainError("Assessment id must not be blank")
        if len(normalized) > ASSESSMENT_ID_MAX_LENGTH:
            raise DomainError(f"Assessment id must be at most {ASSESSMENT_ID_MAX_LENGTH} characters")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def new(cls) -> "AssessmentId":
        """Return a fresh identifier, never used before.

        Returns:
            AssessmentId: ``risk-`` followed by a random UUID.
        """
        return cls(f"{ASSESSMENT_ID_PREFIX}{uuid.uuid4()}")


@dataclass(frozen=True, slots=True)
class Ruc:
    """A Peruvian taxpayer number (Registro Único de Contribuyentes).

    Attributes:
        value (str): Exactly eleven digits, e.g. ``20123456789``.
    """

    value: str

    def __post_init__(self) -> None:
        """Reject anything that is not eleven digits.

        Raises:
            DomainError: If the value is not exactly eleven digits.
        """
        normalized = self.value.strip()
        if len(normalized) != 11 or not normalized.isdigit():
            raise DomainError(f"'{self.value}' is not a RUC: it must be exactly 11 digits")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in one currency.

    Attributes:
        amount (Decimal): Never negative, kept to two decimals.
        currency (Currency): PEN or USD.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        """Reject a negative amount and keep two decimals.

        Raises:
            DomainError: If the amount is negative.
        """
        if self.amount < 0:
            raise DomainError("An amount of money cannot be negative")
        object.__setattr__(self, "amount", self.amount.quantize(Decimal("0.01")))


@dataclass(frozen=True, slots=True)
class Payer:
    """The company that owes the invoice; its risk is what an assessment grades.

    Attributes:
        ruc (Ruc): The payer's taxpayer number.
        name (str): The payer's name as written on the invoice.
    """

    ruc: Ruc
    name: str

    def __post_init__(self) -> None:
        """Reject a blank or overlong name.

        Raises:
            DomainError: If the name is blank or longer than 255 characters.
        """
        normalized = self.name.strip()
        if not normalized:
            raise DomainError("Payer name must not be blank")
        if len(normalized) > PAYER_NAME_MAX_LENGTH:
            raise DomainError(f"Payer name must be at most {PAYER_NAME_MAX_LENGTH} characters")
        object.__setattr__(self, "name", normalized)


@dataclass(frozen=True, slots=True)
class AuctionFacts:
    """What Investment told us about an auction when it was created.

    The grading policy decides from these facts alone, so an assessment can
    always be explained by the facts stored with it.

    Attributes:
        auction_id (AuctionId): The auction being assessed.
        invoice_id (str): The invoice behind the auction, in the Invoicing context.
        mype_id (str): The MYPE that sells the invoice.
        payer (Payer): Who owes the invoice.
        due_date (date): When the payer must pay.
        invoice_amount (Money): The invoice's total.
        green_certified (bool): Whether Investment marked the auction as green.
    """

    auction_id: AuctionId
    invoice_id: str
    mype_id: str
    payer: Payer
    due_date: date
    invoice_amount: Money
    green_certified: bool

    def __post_init__(self) -> None:
        """Reject blank references to the invoice or the MYPE.

        Raises:
            DomainError: If the invoice or MYPE id is blank.
        """
        if not self.invoice_id.strip():
            raise DomainError("Invoice id must not be blank")
        if not self.mype_id.strip():
            raise DomainError("MYPE id must not be blank")


@dataclass(frozen=True, slots=True)
class GradingDecision:
    """What a grading policy concluded about an auction.

    Attributes:
        grade (RiskGrade): The risk class.
        full_balance_outstanding (bool): Whether the invoice's whole balance is
            still owed; Investment only accepts auctions where it is.
        policy_version (str): Which policy decided, so a stored assessment says
            how it was graded.
        provisional (bool): Whether the policy is a stand-in, not a real
            assessment of the payer.
    """

    grade: RiskGrade
    full_balance_outstanding: bool
    policy_version: str
    provisional: bool

    def __post_init__(self) -> None:
        """Reject a decision that does not say which policy made it.

        Raises:
            DomainError: If the policy version is blank.
        """
        if not self.policy_version.strip():
            raise DomainError("A grading decision must name the policy that made it")
