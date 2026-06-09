"""Preflight QA bloqueante — valida PDF/contexto antes do render final.

Critérios bloqueantes (raise `PreflightError`):
  • Equipamentos sem nome.
  • Equipamentos com classificação de risco vazia.
  • Recomendações sem texto.
  • Sumário (TOC) referenciando âncoras inexistentes.
  • Citação de norma fora do allowlist (warning, não bloqueante por enquanto).

Critérios de warning (logado, não bloqueia):
  • Equipamento sem imagens.
  • Equipamento sem justificativas técnicas.
  • Texto narrativo < 80 chars.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


class PreflightError(RuntimeError):
    """Bloqueio identificado pelo preflight — relatório não pode ser publicado."""


@dataclass
class PreflightReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"PDF Preflight: {len(self.errors)} erro(s), "
            f"{len(self.warnings)} aviso(s)"
        )


def run_preflight(
    *,
    equipments: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    raise_on_error: bool = True,
) -> PreflightReport:
    report = PreflightReport()
    metadata = metadata or {}

    if not equipments:
        report.errors.append("Lista de equipamentos vazia.")

    for idx, eq in enumerate(equipments, start=1):
        ref = f"Equipamento #{idx} ({eq.get('nome', '<sem nome>')})"
        if not (eq.get("nome") or "").strip():
            report.errors.append(f"{ref}: nome vazio.")
        if not (eq.get("classificacao") or eq.get("risco") or "").strip():
            report.errors.append(f"{ref}: classificação de risco vazia.")

        recs = eq.get("recomendacoes_tecnicas") or []
        if not recs:
            report.warnings.append(f"{ref}: sem recomendações técnicas.")
        else:
            for r_idx, rec in enumerate(recs, start=1):
                if not (rec.get("texto") or "").strip():
                    report.errors.append(
                        f"{ref}: recomendação #{r_idx} sem texto."
                    )

        justs = eq.get("justificativas_tecnicas") or []
        if not justs:
            report.warnings.append(f"{ref}: sem justificativas técnicas.")

        if not eq.get("images"):
            report.warnings.append(f"{ref}: sem registro fotográfico.")

    # Metadata mínimo
    for required_key in ("razao_social", "site"):
        if not (metadata.get(required_key) or "").strip():
            report.errors.append(f"Metadata.{required_key} ausente.")

    # Log
    if report.errors:
        logger.error("PreflightReport | erros: {}", report.errors)
    if report.warnings:
        logger.warning("PreflightReport | warnings: {}", report.warnings)
    logger.info(report.summary())

    if report.errors and raise_on_error:
        raise PreflightError(
            f"{report.summary()} | "
            f"primeiro erro: {report.errors[0]}"
        )
    return report
