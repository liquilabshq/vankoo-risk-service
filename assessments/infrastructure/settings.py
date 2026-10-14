"""Settings the Assessments context owns, read from ``INVESTMENT_*`` variables."""
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
