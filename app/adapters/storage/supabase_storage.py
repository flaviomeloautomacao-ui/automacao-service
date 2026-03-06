"""Adaptador de storage — Supabase Storage via REST (httpx).

Implementa ``StoragePort`` usando chamadas HTTP diretas à API de Storage
do Supabase, sem depender do SDK ``supabase-py``.

Referência da API:
    https://supabase.com/docs/reference/storage/

Exemplo de uso::

    from app.adapters.storage.supabase_storage import SupabaseStorage

    storage = SupabaseStorage(
        supabase_url="https://xyzcompany.supabase.co",
        service_role_key="eyJ...",
    )
    path = await storage.put_bytes("documents", "uploads/abc/file.xlsx", data)
    url  = await storage.get_signed_url("documents", "uploads/abc/file.xlsx", 3600)
"""

from __future__ import annotations

from typing import Any

import httpx

from app.domain.errors import StorageError


class SupabaseStorage:
    """Implementação concreta de ``StoragePort`` para Supabase Storage.

    Utiliza ``httpx.AsyncClient`` para chamadas HTTP à REST API do Supabase.
    A autenticação é feita via header ``Authorization: Bearer <service_role_key>``
    e ``apikey: <service_role_key>``.
    """

    _UPLOAD_TIMEOUT = 60.0  # segundos — upload de arquivos pode ser lento
    _DEFAULT_TIMEOUT = 15.0

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
    ) -> None:
        """Inicializa o client de storage.

        Args:
            supabase_url: URL do projeto Supabase (ex: ``https://xyz.supabase.co``).
            service_role_key: Chave service-role para autenticação.
        """
        self._base_url = supabase_url.rstrip("/")
        self._key = service_role_key
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _storage_url(self, *segments: str) -> str:
        """Monta a URL completa do endpoint de Storage.

        Args:
            *segments: partes do path (serão unidas com ``/``).

        Returns:
            URL completa como string.
        """
        path = "/".join(s.strip("/") for s in segments if s)
        return f"{self._base_url}/storage/v1/{path}"

    # ------------------------------------------------------------------
    # StoragePort — put_bytes
    # ------------------------------------------------------------------

    async def put_bytes(
        self,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Faz upload de bytes para o Supabase Storage.

        Tenta primeiro um ``POST`` (criação); se o objeto já existir
        (HTTP 400 / ``Duplicate``), faz ``PUT`` (atualização / upsert).

        Args:
            bucket: nome do bucket no Supabase Storage.
            path: caminho do objeto dentro do bucket.
            data: conteúdo binário a armazenar.
            content_type: MIME type do conteúdo.
            metadata: dicionário de metadados customizados (headers ``x-upsert``, etc.).

        Returns:
            Path do objeto armazenado (mesmo ``path`` de entrada).

        Raises:
            StorageError: se o upload falhar.
        """
        url = self._storage_url("object", bucket, path)

        headers = {
            **self._headers,
            "Content-Type": content_type,
            "x-upsert": "true",  # cria ou sobrescreve
        }
        if metadata:
            # Supabase aceita metadados customizados via header JSON
            import json

            headers["x-metadata"] = json.dumps(metadata)

        try:
            async with httpx.AsyncClient(timeout=self._UPLOAD_TIMEOUT) as client:
                response = await client.post(url, content=data, headers=headers)

                if response.status_code in (200, 201):
                    return path

                # Tentar upsert via PUT caso POST retorne conflito
                if response.status_code == 400:
                    response = await client.put(url, content=data, headers=headers)
                    if response.status_code in (200, 201):
                        return path

                raise StorageError(
                    f"Upload falhou ({response.status_code}): {response.text}",
                    detail=response.text,
                )
        except StorageError:
            raise
        except httpx.TimeoutException as exc:
            raise StorageError(
                f"Timeout ao fazer upload para {bucket}/{path}",
            ) from exc
        except Exception as exc:
            raise StorageError(
                f"Erro inesperado no upload para {bucket}/{path}: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # StoragePort — get_signed_url
    # ------------------------------------------------------------------

    async def get_signed_url(
        self,
        bucket: str,
        path: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Gera URL assinada para download de um objeto.

        Args:
            bucket: nome do bucket.
            path: caminho do objeto dentro do bucket.
            expires_seconds: validade da URL em segundos (padrão 1 hora).

        Returns:
            URL assinada completa.

        Raises:
            StorageError: se a geração falhar.
        """
        url = self._storage_url("object", "sign", bucket, path)
        payload: dict[str, Any] = {"expiresIn": expires_seconds}

        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._headers,
                )

                if response.status_code == 200:
                    body = response.json()
                    signed_path = body.get("signedURL", "")
                    # A API retorna um path relativo — montar URL completa
                    if signed_path.startswith("http"):
                        return signed_path
                    return f"{self._base_url}/storage/v1{signed_path}"

                raise StorageError(
                    f"Falha ao gerar signed URL ({response.status_code}): {response.text}",
                    detail=response.text,
                )
        except StorageError:
            raise
        except httpx.TimeoutException as exc:
            raise StorageError(
                f"Timeout ao gerar signed URL para {bucket}/{path}",
            ) from exc
        except Exception as exc:
            raise StorageError(
                f"Erro inesperado ao gerar signed URL: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # StoragePort — delete
    # ------------------------------------------------------------------

    async def delete(self, bucket: str, paths: list[str]) -> None:
        """Remove um ou mais objetos do bucket.

        Args:
            bucket: nome do bucket.
            paths: lista de caminhos a remover.

        Raises:
            StorageError: se a remoção falhar.
        """
        url = self._storage_url("object", bucket)
        payload: dict[str, Any] = {"prefixes": paths}

        try:
            async with httpx.AsyncClient(timeout=self._DEFAULT_TIMEOUT) as client:
                response = await client.request(
                    "DELETE",
                    url,
                    json=payload,
                    headers=self._headers,
                )

                if response.status_code in (200, 204):
                    return

                raise StorageError(
                    f"Falha ao deletar objetos ({response.status_code}): {response.text}",
                    detail=response.text,
                )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(
                f"Erro inesperado ao deletar objetos de {bucket}: {exc}",
            ) from exc
