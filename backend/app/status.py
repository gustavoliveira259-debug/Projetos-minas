"""Regras de situação das atividades e indicadores de aderência.

Convenções
----------
* Datas são diárias e inclusivas: uma atividade de 01/12 a 03/12 dura 3 dias.
* Progresso esperado em uma data de referência = dias *completos* decorridos / duração.
  (No primeiro dia o esperado é 0%; no dia seguinte ao fim é 100%.)
* Uma atividade fica "atrasada" quando o progresso real está mais de TOLERANCIA abaixo
  do esperado, ou quando o prazo venceu sem conclusão; "adiantada" quando está mais
  de TOLERANCIA acima.
"""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from .models import Atividade

TOLERANCIA = float(os.getenv("MINEPLAN_TOLERANCIA", "0.10"))  # 10 pontos percentuais

NAO_INICIADA = "nao_iniciada"
NO_PRAZO = "no_prazo"
ATRASADA = "atrasada"
ADIANTADA = "adiantada"
CONCLUIDA = "concluida"

ROTULOS = {
    NAO_INICIADA: "Não iniciada",
    NO_PRAZO: "No prazo",
    ATRASADA: "Atrasada",
    ADIANTADA: "Adiantada",
    CONCLUIDA: "Concluída",
}


@dataclass
class Situacao:
    status: str
    rotulo: str
    progresso_real: float          # 0..1+ (passa de 1 se produziu acima do plano)
    progresso_esperado: float      # 0..1
    desvio: float                  # real - esperado (ex.: -0.25 = 25 p.p. atrás)
    qtd_realizada: float
    qtd_esperada: float            # quanto já deveria ter sido feito na data de referência
    saldo: float                   # planejado - realizado (>= 0)
    projecao: float                # quantidade projetada ao fim do prazo, no ritmo atual
    impacto_meta: float            # projecao - planejado (negativo = déficit previsto)
    dias_atraso: int               # dias além do fim planejado (vencida ou concluída depois)
    data_conclusao: date | None
    concluida_com_atraso: bool

    def as_dict(self) -> dict:
        return asdict(self)


def duracao_dias(inicio: date, fim: date) -> int:
    return max((fim - inicio).days + 1, 1)


def progresso_esperado(inicio: date, fim: date, ref: date) -> float:
    if ref <= inicio:
        return 0.0
    if ref > fim:
        return 1.0
    return (ref - inicio).days / duracao_dias(inicio, fim)


def _progresso_real(a: Atividade, realizado: float, concluida: bool) -> float:
    if a.qtd_planejada and a.qtd_planejada > 0:
        return realizado / a.qtd_planejada
    if concluida:
        return 1.0
    return (a.progresso_manual or 0.0) / 100.0


def _projecao(a: Atividade, realizado: float, ref: date) -> float:
    """Quantidade prevista ao fim do prazo mantendo o ritmo observado até a referência."""
    planejado = a.qtd_planejada or 0.0
    if planejado <= 0:
        return 0.0
    if ref > a.fim_planejado:
        return realizado                      # prazo vencido: o que entrou no período é o que vale
    if ref <= a.inicio_planejado and realizado == 0:
        return planejado                      # ainda não começou: assume o plano
    inicio = min(a.inicio_real or a.inicio_planejado, a.inicio_planejado)
    dias_trab = (ref - inicio).days           # dias completos com chance de produção
    if dias_trab <= 0:
        return realizado
    janela = (a.fim_planejado - inicio).days + 1
    return realizado / dias_trab * janela


def calcular_situacao(a: Atividade, ref: date | None = None, tolerancia: float = TOLERANCIA) -> Situacao:
    ref = ref or date.today()
    planejado = a.qtd_planejada or 0.0
    realizado = a.qtd_realizada

    atingiu_qtd = planejado > 0 and realizado >= planejado - 1e-9
    manual_100 = planejado <= 0 and (a.progresso_manual or 0) >= 100
    concluida = a.fim_real is not None or atingiu_qtd or manual_100

    real = _progresso_real(a, realizado, concluida)
    esperado = progresso_esperado(a.inicio_planejado, a.fim_planejado, ref)
    desvio = real - esperado

    data_conclusao = None
    dias_atraso = 0

    if concluida:
        status = CONCLUIDA
        data_conclusao = a.fim_real or a.ultimo_apontamento or ref
        dias_atraso = max((data_conclusao - a.fim_planejado).days, 0)
        projecao = realizado if planejado > 0 else 0.0
    else:
        if ref > a.fim_planejado:
            status = ATRASADA
            dias_atraso = (ref - a.fim_planejado).days
        elif ref < a.inicio_planejado:
            status = ADIANTADA if real > 0 else NAO_INICIADA
        elif real <= 0 and esperado <= 0:
            status = NAO_INICIADA
        elif desvio < -tolerancia:
            status = ATRASADA
        elif desvio > tolerancia:
            status = ADIANTADA
        else:
            status = NO_PRAZO
        projecao = _projecao(a, realizado, ref)

    projecao = round(projecao, 2)
    return Situacao(
        status=status,
        rotulo=ROTULOS[status],
        progresso_real=round(real, 4),
        progresso_esperado=round(esperado, 4),
        desvio=round(desvio, 4),
        qtd_realizada=round(realizado, 2),
        qtd_esperada=round(planejado * esperado, 2),
        saldo=round(max(planejado - realizado, 0.0), 2),
        projecao=projecao,
        impacto_meta=round(projecao - planejado, 2) if planejado > 0 else 0.0,
        dias_atraso=dias_atraso,
        data_conclusao=data_conclusao,
        concluida_com_atraso=dias_atraso > 0 and concluida,
    )


def aderencia(atividades: list[Atividade], ref: date | None = None) -> float | None:
    """Aderência ao plano até a data de referência (0..1).

    Média, entre as atividades que já deveriam ter avançado, de min(real/esperado, 1).
    Não soma toneladas com metros e não deixa uma atividade adiantada mascarar outra atrasada.
    """
    ref = ref or date.today()
    notas = []
    for a in atividades:
        s = calcular_situacao(a, ref)
        if s.progresso_esperado <= 0:
            continue
        notas.append(min(s.progresso_real / s.progresso_esperado, 1.0))
    return round(sum(notas) / len(notas), 4) if notas else None


def indicadores(atividades: list[Atividade], ref: date | None = None) -> dict:
    ref = ref or date.today()
    pares = [(a, calcular_situacao(a, ref)) for a in atividades]

    contagem = {k: 0 for k in ROTULOS}
    for _, s in pares:
        contagem[s.status] += 1

    # Produção agrupada por tipo + unidade (nunca soma unidades diferentes).
    prod: dict[tuple, dict] = defaultdict(lambda: dict(planejado=0.0, esperado=0.0, realizado=0.0, projecao=0.0, n=0))
    for a, s in pares:
        if not a.qtd_planejada:
            continue
        g = prod[(a.tipo or "Sem tipo", a.unidade or "")]
        g["planejado"] += a.qtd_planejada
        g["esperado"] += s.qtd_esperada
        g["realizado"] += s.qtd_realizada
        g["projecao"] += s.projecao
        g["n"] += 1
    producao = []
    for (tipo, un), g in sorted(prod.items()):
        producao.append({
            "tipo": tipo, "unidade": un, "atividades": g["n"],
            "planejado": round(g["planejado"], 2),
            "esperado_ate_ref": round(g["esperado"], 2),
            "realizado": round(g["realizado"], 2),
            "projecao": round(g["projecao"], 2),
            "atingimento": round(g["realizado"] / g["planejado"], 4) if g["planejado"] else None,
            "aderencia_ate_ref": round(g["realizado"] / g["esperado"], 4) if g["esperado"] else None,
            "impacto_meta": round(g["projecao"] - g["planejado"], 2),
        })

    por_frente: dict[str, list] = defaultdict(list)
    for a in atividades:
        por_frente[a.frente or "Sem frente"].append(a)
    situacao_por_id = {a.id: s for a, s in pares}
    frentes = []
    for nome, lst in sorted(por_frente.items()):
        sts = [situacao_por_id[a.id].status for a in lst]
        frentes.append({
            "frente": nome,
            "atividades": len(lst),
            "aderencia": aderencia(lst, ref),
            "atrasadas": sts.count(ATRASADA),
            "concluidas": sts.count(CONCLUIDA),
        })

    alertas = sorted(
        (
            {"id": a.id, "codigo": a.codigo, "descricao": a.descricao, "frente": a.frente, "tipo": a.tipo,
             "unidade": a.unidade, "desvio": s.desvio, "dias_atraso": s.dias_atraso, "saldo": s.saldo,
             "impacto_meta": s.impacto_meta, "fim_planejado": a.fim_planejado}
            for a, s in pares if s.status == ATRASADA
        ),
        key=lambda x: (-x["dias_atraso"], x["desvio"]),
    )

    return {
        "data_referencia": ref,
        "tolerancia": TOLERANCIA,
        "total": len(atividades),
        "contagem": contagem,
        "aderencia": aderencia(atividades, ref),
        "producao": producao,
        "frentes": frentes,
        "alertas": alertas,
    }


def semana_iso(d: date) -> str:
    ano, sem, _ = d.isocalendar()
    return f"{ano}-S{sem:02d}"


def inicio_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())
