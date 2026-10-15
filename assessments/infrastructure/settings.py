"""Settings the Assessments context owns, read from ``INVESTMENT_*`` and ``CREDIT_BUREAU_*`` variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class InvestmentSettings(BaseSettings):
    """How assessments reach the Investment service.

    Attributes:
        base_url (str): Investment's own address, never the gateway's: the
            gateway does not route the internal evaluation endpoint.
        connect_timeout (float): Seconds to wait for a connection.
        read_timeout (float): Seconds to wait for the answer.
        delivery_enabled (bool): Start the delivery worker with the
            application. Off in tests and when only running migrations.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="INVESTMENT_", extra="ignore")

    base_url: str = "http://localhost:8082"
    connect_timeout: float = 2.0
    read_timeout: float = 5.0
    delivery_enabled: bool = True


investment_settings = InvestmentSettings()


class CreditBureauSettings(BaseSettings):
    """Whether the scoring asks a credit bureau, read from ``CREDIT_BUREAU_*`` variables.

    Attributes:
        enabled (bool): Ask the (simulated) bureau. With ``false`` the credit
            rating is left out of the score.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CREDIT_BUREAU_", extra="ignore")

    enabled: bool = True


credit_bureau_settings = CreditBureauSettings()
