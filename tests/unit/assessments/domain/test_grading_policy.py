"""The provisional policy: varied, stable and always marked provisional."""
from assessments.domain.services import PROVISIONAL_POLICY_VERSION, ProvisionalHashGradePolicy
from assessments.domain.value_objects import RiskGrade
from tests.fakes import facts


def test_same_auction_always_gets_the_same_grade() -> None:
    policy = ProvisionalHashGradePolicy()
    assert policy.grade(facts("auction-42")) == policy.grade(facts("auction-42"))


def test_grades_are_varied_across_auctions() -> None:
    policy = ProvisionalHashGradePolicy()
    grades = {policy.grade(facts(f"auction-{n}")).grade for n in range(60)}
    assert grades == {RiskGrade.A, RiskGrade.B, RiskGrade.C}


def test_every_decision_is_provisional_and_fully_outstanding() -> None:
    decision = ProvisionalHashGradePolicy().grade(facts())
    assert decision.provisional is True
    assert decision.full_balance_outstanding is True
    assert decision.policy_version == PROVISIONAL_POLICY_VERSION
