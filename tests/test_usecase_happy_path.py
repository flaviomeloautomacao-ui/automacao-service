"""Teste de happy-path do ProcessUploadUseCase.

Todas as dependências externas (storage, banco, LLM, PDF renderer)
são substituídas por mocks/fakes — nenhuma infra real é necessária.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.adapters.spreadsheet.parser import PandasSpreadsheetParser
from app.adapters.spreadsheet.validator import BasicSpreadsheetValidator
from app.application.use_cases.process_upload import ProcessUploadUseCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Colunas da planilha real
_REAL_COLUMNS = [
    "Equipamento",
    "Descrição do equipamento",
    "Riscos",
    "Perigo",
    "Causas Possíveis",
    "Consequências",
    "Categoria da Severidade",
    "Categoria da Probabilidade",
    "Classificação do Risco",
    "Medidas Preventivas Existentes",
    "Medidas Preventivas a Implementar",
    "Observações",
]


def _build_csv_bytes() -> bytes:
    """Cria bytes CSV mínimos válidos simulando o layout real da planilha."""
    header = _REAL_COLUMNS
    data = [
        "Prensa Hidráulica",
        "Prensa 150t",
        "Mecânico",
        "Esmagamento de membros",
        "Falha na proteção",
        "Amputação",
        "IV",
        "Alto",
        "Alto",
        "Barreira",
        "Sensor",
        None,
    ]
    rows: list[list] = [header, data]
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repository() -> AsyncMock:
    """Repositório fake que devolve UUIDs fixos."""
    repo = AsyncMock()
    repo.create_upload.return_value = "upload-0001"
    repo.create_draft.return_value = "draft-0001"
    repo.create_generated.return_value = "report-0001"
    return repo


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Storage fake que aceita puts e devolve URL fixa."""
    storage = AsyncMock()
    storage.put_bytes.return_value = "uploads/upload-0001/file.csv"
    storage.get_signed_url.return_value = "https://storage.example.com/report.pdf?token=abc"
    return storage


@pytest.fixture
def mock_llm() -> AsyncMock:
    """LLM fake que retorna seções narrativas fixas."""
    llm = AsyncMock()
    llm.generate_sections.return_value = {
        "resumo": "Resumo executivo do laudo.",
        "recomendacoes": ["Instalar proteções nas prensas."],
        "justificativas": ["Conforme NR-12, item 12.38."],
    }
    return llm


@pytest.fixture
def mock_pdf_renderer() -> MagicMock:
    """Renderer fake que devolve bytes PDF fictícios.

    Não simula ``WeasyPdfRenderer`` (isinstance = False), então o use case
    segue o fallback genérico: renderiza Jinja2 + chama ``render(html)``.
    """
    renderer = MagicMock()
    renderer.render.return_value = b"%PDF-1.4 fake content"
    return renderer


@pytest.fixture
def use_case(
    mock_repository: AsyncMock,
    mock_storage: AsyncMock,
    mock_llm: AsyncMock,
    mock_pdf_renderer: MagicMock,
) -> ProcessUploadUseCase:
    """Instância do use case com todas as dependências mockadas."""
    return ProcessUploadUseCase(
        repository=mock_repository,
        storage=mock_storage,
        parser=PandasSpreadsheetParser(),
        validator=BasicSpreadsheetValidator(),
        llm=mock_llm,
        pdf_renderer=mock_pdf_renderer,
        bucket="test-bucket",
    )


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """Pipeline completo: upload → parse → validação → LLM → PDF → resultado."""

    @pytest.mark.asyncio
    async def test_execute_retorna_ids_e_url(
        self,
        use_case: ProcessUploadUseCase,
        mock_repository: AsyncMock,
        mock_storage: AsyncMock,
        mock_llm: AsyncMock,
        mock_pdf_renderer: MagicMock,
    ) -> None:
        """O execute deve retornar upload_id, draft_id, report_id e pdf_url."""
        csv_bytes = _build_csv_bytes()

        result = await use_case.execute(
            file_bytes=csv_bytes,
            filename="riscos.csv",
            content_type="text/csv",
        )

        # Resultado contém as 4 chaves esperadas
        assert "upload_id" in result
        assert "draft_id" in result
        assert "report_id" in result
        assert "pdf_url" in result

    @pytest.mark.asyncio
    async def test_storage_recebe_arquivo_original(
        self,
        use_case: ProcessUploadUseCase,
        mock_storage: AsyncMock,
    ) -> None:
        """O storage deve receber o arquivo cru na etapa 1."""
        csv_bytes = _build_csv_bytes()

        await use_case.execute(
            file_bytes=csv_bytes,
            filename="riscos.csv",
            content_type="text/csv",
        )

        # put_bytes chamado pelo menos 2x: upload original + PDF
        assert mock_storage.put_bytes.call_count >= 2

    @pytest.mark.asyncio
    async def test_repository_cria_upload_draft_e_report(
        self,
        use_case: ProcessUploadUseCase,
        mock_repository: AsyncMock,
    ) -> None:
        """O repositório deve receber create_upload, create_draft e create_generated."""
        csv_bytes = _build_csv_bytes()

        await use_case.execute(
            file_bytes=csv_bytes,
            filename="riscos.csv",
            content_type="text/csv",
        )

        mock_repository.create_upload.assert_called_once()
        mock_repository.create_draft.assert_called_once()
        mock_repository.create_generated.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_recebe_contexto_com_rows(
        self,
        use_case: ProcessUploadUseCase,
        mock_llm: AsyncMock,
    ) -> None:
        """O LLM deve ser chamado com contexto contendo as linhas de risco."""
        csv_bytes = _build_csv_bytes()

        await use_case.execute(
            file_bytes=csv_bytes,
            filename="riscos.csv",
            content_type="text/csv",
        )

        mock_llm.generate_sections.assert_called_once()
        ctx = mock_llm.generate_sections.call_args[0][0]
        assert "rows" in ctx
        assert ctx["total_rows"] == 1

    @pytest.mark.asyncio
    async def test_pdf_url_presente_no_resultado(
        self,
        use_case: ProcessUploadUseCase,
        mock_storage: AsyncMock,
    ) -> None:
        """A URL assinada do storage deve aparecer no resultado final."""
        csv_bytes = _build_csv_bytes()

        result = await use_case.execute(
            file_bytes=csv_bytes,
            filename="riscos.csv",
            content_type="text/csv",
        )

        assert result["pdf_url"] == "https://storage.example.com/report.pdf?token=abc"
        mock_storage.get_signed_url.assert_called_once()
