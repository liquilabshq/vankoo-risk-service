"""Readers of the files SUNAT publishes.

The padrón reducido del RUC is a ZIP with one text file of about 1.6 GB:
latin-1, ``|``-separated with a trailing ``|``, 15 columns, ``-`` for an empty
value, and no quoting. Some names contain a ``|`` themselves, so a line can
have more fields than columns; the RUC is always first and the last 13 columns
are fixed, so whatever lies between them is the name.

The registry of IGV agents is a ZIP with one UTF-8 CSV (quoted, since names
contain commas) of a few thousand rows, one per RUC and agent role.

Both readers stream: they never hold a whole file in memory. A line that cannot
be read yields ``None``, so the caller can count it as rejected.
"""
import csv
import io
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

from registries.domain.value_objects import AgentRecord, AgentType, TaxpayerRecord
from shared.domain.exceptions import DomainError

TAXPAYER_COLUMNS = 15
FIXED_TRAILING_COLUMNS = 13
EMPTY = "-"
MAX_STATUS_LENGTH = 40


def read_taxpayers(file: Path) -> Iterator[TaxpayerRecord | None]:
    """Yield every row of a padrón reducido ZIP, skipping its header.

    Args:
        file (Path): The downloaded ``padron_reducido_ruc.zip``.

    Yields:
        TaxpayerRecord | None: One record per line, or ``None`` for a line that
        cannot be read.
    """
    with zipfile.ZipFile(file) as archive, archive.open(_single_member(archive, ".txt")) as raw:
        text = io.TextIOWrapper(raw, encoding="latin-1", newline=None)
        for number, line in enumerate(text):
            if number == 0 and line.startswith("RUC|"):
                continue
            yield parse_taxpayer_line(line)


def parse_taxpayer_line(line: str) -> TaxpayerRecord | None:
    """Read one line of the padrón reducido.

    Args:
        line (str): The line, with or without its line break.

    Returns:
        TaxpayerRecord | None: The record, or ``None`` if the line has too few
        fields or no valid RUC.
    """
    fields = line.rstrip("\r\n").split("|")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) < TAXPAYER_COLUMNS:
        return None
    ruc = fields[0].strip()
    name = "|".join(fields[1 : len(fields) - FIXED_TRAILING_COLUMNS]).strip()
    status, condition, ubigeo = (value.strip() for value in fields[-FIXED_TRAILING_COLUMNS:][:3])
    try:
        return TaxpayerRecord(
            ruc=ruc,
            name="" if name == EMPTY else name,
            status=status[:MAX_STATUS_LENGTH],
            domicile_condition=condition[:MAX_STATUS_LENGTH],
            ubigeo=ubigeo if ubigeo.isdigit() and len(ubigeo) == 6 else None,
        )
    except DomainError:
        return None


def read_agents(file: Path) -> Iterator[AgentRecord | None]:
    """Yield every row of the open-data registry of IGV agents.

    Args:
        file (Path): The downloaded ``padron_agentes_retencion_percepcion_igv_YYYYMM.zip``.

    Yields:
        AgentRecord | None: One record per row, or ``None`` for a row that
        cannot be read.
    """
    with zipfile.ZipFile(file) as archive, archive.open(_single_member(archive, ".csv")) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        for row in csv.DictReader(text):
            yield parse_agent_row(row)


def parse_agent_row(row: dict[str, str | None]) -> AgentRecord | None:
    """Read one row of the agents CSV (``fecha_corte,RUC,nombre_o_razon_social,fecha_alta,…``).

    Returns:
        AgentRecord | None: The record, or ``None`` if the RUC or the role cannot be read.
    """
    agent_type = agent_type_from_label(row.get("tipo_agente") or "")
    if agent_type is None:
        return None
    resolution = (row.get("numero_resolucion") or "").strip() or None
    try:
        return AgentRecord(
            ruc=(row.get("RUC") or "").strip(),
            agent_type=agent_type,
            since=_parse_date(row.get("fecha_alta") or ""),
            resolution=resolution[:120] if resolution else None,
        )
    except DomainError:
        return None


def agent_type_from_label(label: str) -> AgentType | None:
    """Map SUNAT's wording (``agente de retención del IGV``…) to an agent role."""
    normalized = _without_accents(label).lower()
    if "retencion" in normalized:
        return AgentType.WITHHOLDING
    if "hidrocarburo" in normalized:
        return AgentType.PERCEPTION_FUEL
    if "percepcion" in normalized:
        return AgentType.PERCEPTION_DOMESTIC_SALES
    return None


def _parse_date(value: str) -> date | None:
    value = value.strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _without_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _single_member(archive: zipfile.ZipFile, extension: str) -> str:
    names = [name for name in archive.namelist() if name.lower().endswith(extension)]
    if len(names) != 1:
        raise ValueError(f"Expected one {extension} file in the archive, found {names}")
    return names[0]
