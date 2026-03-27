"""Nomenclatura padronizada de imagens de equipamento.

Formato obrigatório: ``NomeEquipamentoContrato_ContratoId-Index``

Regras:
  - ``NomeEquipamentoContrato``: PascalCase, sem espaços/hífens/caracteres especiais.
    Pode conter números (ex: ``SiloBaiaNorte2``).
  - ``ContratoId``: identificador do contrato, após o separador ``_``
  - ``Index``: obrigatório, começa em 0, incremental, separado por ``-``

Exemplos válidos::

    MoegaFerroviaria1720_123412341234-0
    SiloBaiaNorte2_12341234-0

Exemplos inválidos::

    moegaferroviaria1720_123412341234-0  → não é PascalCase
    MoegaFerroviaria1720_123412341234    → sem índice
    MoegaRodoviaria-1720_12341234-2     → caractere inválido no nome
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ─── Regex central de validação ────────────────────────────

EQUIPMENT_IMAGE_NAME_REGEX = re.compile(
    r"^[A-Z][a-zA-Z0-9]*_[a-zA-Z0-9]+-\d+$"
)

# ─── Data classes ──────────────────────────────────────────


@dataclass(frozen=True)
class ImageNameValidationError:
    """Erro de validação de nome de imagem."""

    code: str
    message: str


@dataclass
class ImageNameValidationResult:
    """Resultado da validação de nome de imagem."""

    valid: bool
    errors: list[ImageNameValidationError] = field(default_factory=list)
    equipment_name: str | None = None
    contrato_id: str | None = None
    index: int | None = None


@dataclass(frozen=True)
class ParsedImageName:
    """Nome de imagem parseado."""

    equipment_name: str
    contrato_id: str
    index: int
    extension: str = ""


# ─── Funções de normalização ──────────────────────────────


def _strip_accents(text: str) -> str:
    """Remove acentos/diacríticos de um texto."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def to_pascal_case(name: str) -> str:
    """Converte nome de equipamento para PascalCase.

    Remove acentos, parênteses e caracteres não alfanuméricos.
    Cada "palavra" começa com maiúscula.

    Examples::

        >>> to_pascal_case("Moega Ferroviária 1720")
        'MoegaFerroviaria1720'
        >>> to_pascal_case("silo baía norte 2")
        'SiloBaiaNorte2'
        >>> to_pascal_case("MOEGA FERROVIARIA 1720")
        'MoegaFerroviaria1720'
    """
    text = _strip_accents(name)
    text = text.replace("(", "").replace(")", "")
    words = re.split(r"[\s\-_]+", text)
    parts: list[str] = []
    for word in words:
        clean = re.sub(r"[^a-zA-Z0-9]", "", word)
        if not clean:
            continue
        parts.append(clean[0].upper() + clean[1:].lower())
    return "".join(parts)


def sanitize_contrato_id(contrato: str) -> str:
    """Remove caracteres não alfanuméricos do ID do contrato."""
    return re.sub(r"[^a-zA-Z0-9]", "", contrato)


# ─── Geração de nome padronizado ──────────────────────────


def generate_image_name(
    equipment_name: str,
    contrato_id: str,
    index: int,
) -> str:
    """Gera nome de imagem no formato ``NomeEquipamento_ContratoId-Index``.

    Args:
        equipment_name: Nome original do equipamento.
        contrato_id: Identificador do contrato.
        index: Índice da imagem (>= 0).

    Returns:
        Nome padronizado (sem extensão).

    Example::

        >>> generate_image_name("Moega Ferroviária 1720", "123412341234", 0)
        'MoegaFerroviaria1720_123412341234-0'
    """
    pascal = to_pascal_case(equipment_name)
    sanitized_contrato = sanitize_contrato_id(contrato_id)
    safe_index = max(0, int(index))
    return f"{pascal}_{sanitized_contrato}-{safe_index}"


def generate_image_filename(
    equipment_name: str,
    contrato_id: str,
    index: int,
    extension: str = "jpg",
) -> str:
    """Gera nome de arquivo completo com extensão.

    Example::

        >>> generate_image_filename("Moega Ferroviária 1720", "123412341234", 0, "png")
        'MoegaFerroviaria1720_123412341234-0.png'
    """
    name = generate_image_name(equipment_name, contrato_id, index)
    ext = extension.lstrip(".").lower()
    return f"{name}.{ext}"


# ─── Validação robusta ────────────────────────────────────


def validate_image_name(image_name: str) -> ImageNameValidationResult:
    """Valida um nome de imagem contra o padrão obrigatório.

    Args:
        image_name: Nome da imagem SEM extensão.

    Returns:
        Resultado com ``valid``, ``errors`` e partes parseadas.

    Example::

        >>> r = validate_image_name("MoegaFerroviaria1720_123412341234-0")
        >>> r.valid
        True
        >>> r = validate_image_name("moegaferroviaria1720_123412341234-0")
        >>> r.valid
        False
        >>> r.errors[0].code
        'NOT_PASCAL_CASE'
    """
    errors: list[ImageNameValidationError] = []

    if not image_name or not image_name.strip():
        return ImageNameValidationResult(
            valid=False,
            errors=[ImageNameValidationError("EMPTY_NAME", "Nome da imagem é obrigatório.")],
        )

    trimmed = image_name.strip()

    # Verificar separador underscore
    underscore_idx = trimmed.find("_")
    if underscore_idx == -1:
        errors.append(ImageNameValidationError(
            "MISSING_UNDERSCORE",
            f"Nome deve conter '_' separando o nome do equipamento e o contrato. "
            f"Padrão: NomeEquipamento_ContratoId-Index",
        ))
        return ImageNameValidationResult(valid=False, errors=errors)

    equipment_part = trimmed[:underscore_idx]
    rest = trimmed[underscore_idx + 1:]

    if not equipment_part:
        errors.append(ImageNameValidationError(
            "EMPTY_EQUIPMENT_NAME",
            "Nome do equipamento (antes de '_') não pode estar vazio.",
        ))

    # Verificar separador de índice
    last_dash_idx = rest.rfind("-")
    if last_dash_idx == -1:
        errors.append(ImageNameValidationError(
            "MISSING_INDEX",
            "Nome deve conter índice após '-'. Padrão: NomeEquipamento_ContratoId-Index",
        ))
        return ImageNameValidationResult(valid=False, errors=errors)

    contrato_part = rest[:last_dash_idx]
    index_part = rest[last_dash_idx + 1:]

    if not contrato_part:
        errors.append(ImageNameValidationError(
            "EMPTY_CONTRATO",
            "ContratoId (entre '_' e '-') não pode estar vazio.",
        ))

    # Validar índice
    parsed_index = -1
    if not index_part or not index_part.isdigit():
        errors.append(ImageNameValidationError(
            "INVALID_INDEX",
            f"Índice '{index_part}' deve ser um número inteiro >= 0.",
        ))
    else:
        parsed_index = int(index_part)

    # Validar PascalCase no nome do equipamento
    if equipment_part:
        if not equipment_part[0].isupper():
            errors.append(ImageNameValidationError(
                "NOT_PASCAL_CASE",
                f"Nome do equipamento '{equipment_part}' deve começar com letra maiúscula (PascalCase).",
            ))
        if re.search(r"[^a-zA-Z0-9]", equipment_part):
            errors.append(ImageNameValidationError(
                "INVALID_CHARACTERS",
                f"Nome do equipamento '{equipment_part}' contém caracteres inválidos. "
                f"Use apenas letras e números.",
            ))

    # Validar caracteres no contrato
    if contrato_part and re.search(r"[^a-zA-Z0-9]", contrato_part):
        errors.append(ImageNameValidationError(
            "INVALID_CHARACTERS",
            f"ContratoId '{contrato_part}' contém caracteres inválidos. "
            f"Use apenas letras e números.",
        ))

    # Verificação final com regex
    if not errors and not EQUIPMENT_IMAGE_NAME_REGEX.match(trimmed):
        errors.append(ImageNameValidationError(
            "REGEX_MISMATCH",
            f"Nome '{trimmed}' não corresponde ao padrão obrigatório.",
        ))

    return ImageNameValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        equipment_name=equipment_part if equipment_part else None,
        contrato_id=contrato_part if contrato_part else None,
        index=parsed_index if parsed_index >= 0 else None,
    )


def validate_image_filename(filename: str) -> ImageNameValidationResult:
    """Valida um nome de arquivo completo (remove extensão antes de validar)."""
    without_ext = re.sub(r"\.[^.]+$", "", filename)
    return validate_image_name(without_ext)


# ─── Parsing ──────────────────────────────────────────────


def parse_image_filename(filename: str) -> ParsedImageName | None:
    """Parseia um nome de arquivo de imagem no novo formato.

    Returns:
        ``ParsedImageName`` ou ``None`` se o nome não segue o padrão.

    Example::

        >>> r = parse_image_filename("MoegaFerroviaria1720_123412341234-0.jpg")
        >>> r.equipment_name
        'MoegaFerroviaria1720'
        >>> r.index
        0
    """
    ext_match = re.search(r"\.([^.]+)$", filename)
    extension = ext_match.group(1).lower() if ext_match else ""
    without_ext = re.sub(r"\.[^.]+$", "", filename)

    result = validate_image_name(without_ext)
    if not result.valid or result.equipment_name is None:
        return None

    return ParsedImageName(
        equipment_name=result.equipment_name,
        contrato_id=result.contrato_id or "",
        index=result.index if result.index is not None else 0,
        extension=extension,
    )


# ─── Cálculo do próximo índice ────────────────────────────


def get_next_image_index(existing_image_names: list[str]) -> int:
    """Calcula o próximo índice disponível para imagens de um equipamento.

    Args:
        existing_image_names: Nomes de imagem existentes (sem extensão ou public_ids).

    Returns:
        Próximo índice disponível.

    Example::

        >>> get_next_image_index(["MoegaFerroviaria1720_1234-0", "MoegaFerroviaria1720_1234-1"])
        2
        >>> get_next_image_index([])
        0
    """
    max_index = -1
    for name in existing_image_names:
        base = re.sub(r"\.[^.]+$", "", name)
        match = re.search(r"-(\d+)$", base)
        if match:
            idx = int(match.group(1))
            if idx > max_index:
                max_index = idx
    return max_index + 1


# ─── Normalização legada (backward-compatibility) ─────────


def normalize_equipment_name_legacy(name: str) -> str:
    """Normaliza o nome de um equipamento para lowercase (padrão legado).

    .. deprecated::
        Usar ``to_pascal_case`` para novos nomes.
    """
    text = _strip_accents(name)
    text = text.replace("(", "").replace(")", "")
    text = re.sub(r"[^a-zA-Z0-9]", "", text)
    return text.lower()
