"""Domain services of the Assessments bounded context.

The grading policy is the rule that turns an auction's facts into a grade. It
belongs to no single aggregate: it reads facts that come from Investment and,
in later phases, from public registries. It is a port so that the policy can be
replaced without touching the assessment, the consumer or the delivery.
"""
import hashlib
from abc import ABC, abstractmethod

from assessments.domain.value_objects import AuctionFacts, GradingDecision, RiskGrade

PROVISIONAL_POLICY_VERSION = "provisional-hash-v0"


class RiskGradingPolicy(ABC):
    """Decides the grade of an auction from its facts, with no I/O."""

    @abstractmethod
    def grade(self, facts: AuctionFacts) -> GradingDecision:
        """Grade an auction.

        Args:
            facts (AuctionFacts): What Investment published about the auction.

        Returns:
            GradingDecision: The grade and the policy that gave it.
        """


class ProvisionalHashGradePolicy(RiskGradingPolicy):
    """PROVISIONAL stand-in: a grade derived from the auction id, not from its risk.

    TEMPORARY. It exists so the whole path (Kafka, assessment, delivery to
    Investment) works before the real rules exist; it replaces the simulated
    evaluation Investment used to run itself. The grade says nothing about the
    payer. It is varied, so the marketplace still shows different rates, and
    stable, so the same auction always gets the same grade. Every decision is
    marked ``provisional``. Phase 2 replaces it with the points-based policy;
    see ``docs/PROVISIONAL_RISK_GRADE.md``.
    """

    _GRADES = (RiskGrade.A, RiskGrade.B, RiskGrade.C)

    def grade(self, facts: AuctionFacts) -> GradingDecision:
        digest = hashlib.sha256(facts.auction_id.value.encode()).digest()
        return GradingDecision(
            grade=self._GRADES[int.from_bytes(digest[:8], "big") % len(self._GRADES)],
            full_balance_outstanding=True,
            policy_version=PROVISIONAL_POLICY_VERSION,
            provisional=True,
        )
