"""Settings the Registries context owns, read from ``REGISTRY_*`` variables."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class RegistrySettings(BaseSettings):
    """Where SUNAT publishes its registries, and when to refresh the local copy.

    Attributes:
        taxpayers_url (str): The padrón reducido del RUC (a ZIP of about 400 MB,
            rebuilt every day).
        agents_url_template (str): The monthly registry of IGV withholding and
            perception agents on the national open-data portal; ``{period}`` is
            ``YYYYMM``.
        agents_months_back (int): How many months back to look for the latest
            agents file, since the current month may not be published yet.
        user_agent (str): Sent with every request. The open-data portal answers
            418 to clients that do not look like a browser.
        download_timeout (float): Seconds to wait for any single read while downloading.
        refresh_enabled (bool): Refresh the registries from the running service:
            once at start-up and every day at ``refresh_hour``.
        refresh_hour (int): Hour of the daily refresh, in ``timezone``. SUNAT
            rebuilds the padrón around 02:30 Lima time.
        timezone (str): Time zone of ``refresh_hour``.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="REGISTRY_", extra="ignore")

    taxpayers_url: str = "https://www2.sunat.gob.pe/padron_reducido_ruc.zip"
    agents_url_template: str = (
        "https://www.datosabiertos.gob.pe/sites/default/files/padron_agentes_retencion_percepcion_igv_{period}.zip"
    )
    agents_months_back: int = 4
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36 VankooRiskService/0.2"
    )
    download_timeout: float = 120.0
    refresh_enabled: bool = True
    refresh_hour: int = 4
    timezone: str = "America/Lima"


registry_settings = RegistrySettings()
