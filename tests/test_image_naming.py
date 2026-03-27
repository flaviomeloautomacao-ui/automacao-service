"""Testes — image_naming (nomenclatura de imagens de equipamento).

Cobre:
  1. to_pascal_case — diversos formatos de entrada
  2. sanitize_contrato_id — remoção de caracteres inválidos
  3. generate_image_name — geração de nome padronizado
  4. validate_image_name — nomes válidos e inválidos
  5. parse_image_filename — parsing com extensão
  6. get_next_image_index — cálculo de próximo índice
  7. Edge cases — strings vazias, caracteres especiais, duplicatas

Run: pytest tests/test_image_naming.py -v
"""

from __future__ import annotations

import pytest

from app.domain.image_naming import (
    EQUIPMENT_IMAGE_NAME_REGEX,
    ImageNameValidationError,
    to_pascal_case,
    sanitize_contrato_id,
    generate_image_name,
    generate_image_filename,
    validate_image_name,
    validate_image_filename,
    parse_image_filename,
    get_next_image_index,
    normalize_equipment_name_legacy,
)


# ─── 1. to_pascal_case ──────────────────────────────────────


class TestToPascalCase:
    def test_accents_and_spaces(self):
        assert to_pascal_case("Moega Ferroviária 1720") == "MoegaFerroviaria1720"

    def test_lowercase_input(self):
        assert to_pascal_case("silo baía norte 2") == "SiloBaiaNorte2"

    def test_uppercase_input(self):
        assert to_pascal_case("MOEGA FERROVIARIA 1720") == "MoegaFerroviaria1720"

    def test_parentheses_removed(self):
        assert to_pascal_case("Moega 1720 (rodoviária)") == "Moega1720Rodoviaria"

    def test_hyphens_and_underscores(self):
        assert to_pascal_case("silo-norte_2") == "SiloNorte2"

    def test_multiple_spaces(self):
        assert to_pascal_case("  elevador  de  canecas  ") == "ElevadorDeCanecas"

    def test_empty_string(self):
        assert to_pascal_case("") == ""


# ─── 2. sanitize_contrato_id ────────────────────────────────


class TestSanitizeContratoId:
    def test_removes_hyphens(self):
        assert sanitize_contrato_id("1234-5678/90") == "1234567890"

    def test_alphanumeric_preserved(self):
        assert sanitize_contrato_id("ABC123") == "ABC123"

    def test_empty(self):
        assert sanitize_contrato_id("") == ""


# ─── 3. generate_image_name ─────────────────────────────────


class TestGenerateImageName:
    def test_full_format(self):
        assert (
            generate_image_name("Moega Ferroviária 1720", "123412341234", 0)
            == "MoegaFerroviaria1720_123412341234-0"
        )

    def test_another_equipment(self):
        assert (
            generate_image_name("Silo Baía Norte 2", "12341234", 0)
            == "SiloBaiaNorte2_12341234-0"
        )

    def test_index_greater_than_zero(self):
        assert (
            generate_image_name("Moega Ferroviária 1720", "123412341234", 3)
            == "MoegaFerroviaria1720_123412341234-3"
        )

    def test_contrato_with_hyphen(self):
        assert generate_image_name("Elevator", "ABC-123", 0) == "Elevator_ABC123-0"

    def test_negative_index_clamped(self):
        assert generate_image_name("Test", "1234", -5) == "Test_1234-0"


# ─── 4. generate_image_filename ──────────────────────────────


class TestGenerateImageFilename:
    def test_with_jpg(self):
        assert (
            generate_image_filename("Moega Ferroviária 1720", "123412341234", 0, "jpg")
            == "MoegaFerroviaria1720_123412341234-0.jpg"
        )

    def test_extension_normalized(self):
        assert generate_image_filename("Silo", "1234", 1, ".PNG") == "Silo_1234-1.png"


# ─── 5. validate_image_name — Válidos ───────────────────────


class TestValidateImageNameValid:
    @pytest.mark.parametrize(
        "name",
        [
            "MoegaFerroviaria1720_123412341234-0",
            "SiloBaiaNorte2_12341234-0",
            "Elevator_ABC123-5",
            "A_B-0",
            "MoegaSuperGrande123_Contrato999-99",
        ],
    )
    def test_valid_names(self, name: str):
        result = validate_image_name(name)
        assert result.valid is True
        assert result.errors == []
        assert result.equipment_name is not None
        assert result.contrato_id is not None
        assert result.index is not None and result.index >= 0


# ─── 6. validate_image_name — Inválidos ─────────────────────


class TestValidateImageNameInvalid:
    def test_lowercase_not_pascal(self):
        r = validate_image_name("moegaferroviaria1720_123412341234-0")
        assert r.valid is False
        assert any(e.code == "NOT_PASCAL_CASE" for e in r.errors)

    def test_missing_index(self):
        r = validate_image_name("MoegaFerroviaria1720_123412341234")
        assert r.valid is False
        assert any(e.code == "MISSING_INDEX" for e in r.errors)

    def test_hyphen_in_name(self):
        r = validate_image_name("MoegaRodoviaria-1720_12341234-2")
        assert r.valid is False
        assert any(e.code == "INVALID_CHARACTERS" for e in r.errors)

    def test_empty_string(self):
        r = validate_image_name("")
        assert r.valid is False
        assert any(e.code == "EMPTY_NAME" for e in r.errors)

    def test_no_underscore(self):
        r = validate_image_name("NomeEquipamento")
        assert r.valid is False
        assert any(e.code == "MISSING_UNDERSCORE" for e in r.errors)

    def test_empty_equipment_name(self):
        r = validate_image_name("_1234-0")
        assert r.valid is False
        assert any(e.code == "EMPTY_EQUIPMENT_NAME" for e in r.errors)

    def test_empty_contrato(self):
        r = validate_image_name("Moega_-0")
        assert r.valid is False
        assert any(e.code == "EMPTY_CONTRATO" for e in r.errors)

    def test_non_numeric_index(self):
        r = validate_image_name("Moega_1234-abc")
        assert r.valid is False
        assert any(e.code == "INVALID_INDEX" for e in r.errors)

    def test_space_in_name(self):
        r = validate_image_name("Moega Rodoviaria_1234-0")
        assert r.valid is False
        assert any(e.code == "INVALID_CHARACTERS" for e in r.errors)


# ─── 7. validate_image_filename ──────────────────────────────


class TestValidateImageFilename:
    def test_valid_with_extension(self):
        r = validate_image_filename("MoegaFerroviaria1720_123412341234-0.jpg")
        assert r.valid is True

    def test_invalid_with_extension(self):
        r = validate_image_filename("moega_1234-0.png")
        assert r.valid is False


# ─── 8. parse_image_filename ────────────────────────────────


class TestParseImageFilename:
    def test_parse_success(self):
        r = parse_image_filename("MoegaFerroviaria1720_123412341234-0.jpg")
        assert r is not None
        assert r.equipment_name == "MoegaFerroviaria1720"
        assert r.contrato_id == "123412341234"
        assert r.index == 0
        assert r.extension == "jpg"

    def test_parse_index_3(self):
        r = parse_image_filename("SiloBaiaNorte2_12341234-3.png")
        assert r is not None
        assert r.index == 3

    def test_parse_invalid(self):
        r = parse_image_filename("invalid-name.jpg")
        assert r is None


# ─── 9. get_next_image_index ────────────────────────────────


class TestGetNextImageIndex:
    def test_empty_list(self):
        assert get_next_image_index([]) == 0

    def test_two_existing(self):
        assert get_next_image_index([
            "MoegaFerroviaria1720_1234-0",
            "MoegaFerroviaria1720_1234-1",
        ]) == 2

    def test_with_full_path(self):
        assert get_next_image_index([
            "reports/xyz/equipments/MoegaFerroviaria1720_1234-0",
        ]) == 1

    def test_gap_in_index(self):
        assert get_next_image_index(["Moega_1234-5"]) == 6

    def test_no_index_format(self):
        assert get_next_image_index(["old-format-without-index"]) == 0


# ─── 10. Regex ──────────────────────────────────────────────


class TestRegex:
    @pytest.mark.parametrize(
        "name",
        [
            "MoegaFerroviaria1720_123412341234-0",
            "SiloBaiaNorte2_12341234-0",
            "A_B-0",
        ],
    )
    def test_valid_regex(self, name: str):
        assert EQUIPMENT_IMAGE_NAME_REGEX.match(name) is not None

    @pytest.mark.parametrize(
        "name",
        [
            "moega_1234-0",
            "Moega_1234",
            "Moega-Rodo_1234-0",
            "_1234-0",
            "Moega_-0",
        ],
    )
    def test_invalid_regex(self, name: str):
        assert EQUIPMENT_IMAGE_NAME_REGEX.match(name) is None


# ─── 11. Backward compatibility ─────────────────────────────


class TestLegacyNormalize:
    def test_legacy_format(self):
        assert normalize_equipment_name_legacy("Moega 1720 (rodoviária)") == "moega1720rodoviaria"
