"""Adapter that downloads certificates from Profile's bucket over HTTP.

Profile's bucket allows anonymous reads (its ``fileUrl`` is public), so a plain
GET is enough. The base URL is this service's own way into the bucket, never
one that arrives in an event: the event only names the object key, which the
domain already checked is under a company's sustainability folder.
"""
import httpx

from sustainability.application.outbound_services import (
    CertificateDocuments,
    DocumentRejectedError,
    TemporarilyUnavailableError,
)
from sustainability.domain.value_objects import CertificateDocument, DocumentType

# What each type starts with, so a renamed file is not read as what it is not.
MAGIC_NUMBERS = {
    DocumentType.PDF: (b"%PDF-",),
    DocumentType.JPEG: (b"\xff\xd8\xff",),
    DocumentType.PNG: (b"\x89PNG\r\n\x1a\n",),
}


class HttpxCertificateDocuments(CertificateDocuments):
    """Downloads certificates with a process-wide httpx client."""

    def __init__(self, client: httpx.AsyncClient, max_bytes: int) -> None:
        """Initialize the adapter.

        Args:
            client (httpx.AsyncClient): A client whose ``base_url`` is the bucket's.
            max_bytes (int): The largest file accepted.
        """
        self._client = client
        self._max_bytes = max_bytes

    async def fetch(self, document: CertificateDocument) -> bytes:
        try:
            async with self._client.stream("GET", document.object_key) as response:
                if response.status_code in (httpx.codes.NOT_FOUND, httpx.codes.FORBIDDEN):
                    raise DocumentRejectedError("No se encontró el archivo del certificado")
                if not response.is_success:
                    raise TemporarilyUnavailableError(f"The storage answered HTTP {response.status_code}")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > self._max_bytes:
                        raise DocumentRejectedError(
                            f"El archivo supera el máximo de {self._max_bytes // (1024 * 1024)} MB"
                        )
        except httpx.HTTPError as error:
            raise TemporarilyUnavailableError(f"{type(error).__name__}: {error}") from error
        if not content.startswith(MAGIC_NUMBERS[document.document_type]):
            raise DocumentRejectedError("El archivo no es un PDF, JPG o PNG válido")
        return bytes(content)
