"""Indicadores de frota: disponibilidade, utilização, manutenção e conflitos com o planejamento.

Convenções
----------
* Janela de análise = período selecionado (dias inteiros), em horas-calendário (24 h/dia).
* "Até a referência" = do início do período até o fim do dia de referência (ou até agora, se for hoje).
* Disponibilidade física (DF) = (horas calendário − horas em manutenção) ÷ horas calendário.
  Só paradas *corretiva* e *preventiva* contam como manutenção.
* Utilização física (UF) = horas trabalhadas ÷ horas disponíveis. Só é calculada quando há
  apontamento de horas no período.
* DF prevista = mesma conta para o período inteiro, incluindo manutenções já programadas.
* Uma atividade usa um equipamento quando o código dele aparece no campo "Equipamento"
  da atividade. "CM-07/08/09" é lido como CM-07, CM-08 e CM-09.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .models import Atividade, Equipamento, Parada
from .status import CONCLUIDA, calcular_situacao

MANUTENCAO = ("corretiva", "preventiva")
TIPOS_PARADA = {"corretiva": "Corretiva", "preventiva": "Preventiva", "operacional": "Operacional"}

STATUS_EQ = {
    "manutencao": "Em manutenção",
    "parado": "Parado",
    "operando": "Em operação",
    "disponivel": "Disponível",
    "inativo": "Inativo",
}

# Avisa da preventiva quando faltam até 10% do intervalo (mínimo 25 h).
MARGEM_PREVENTIVA = 0.10
MARGEM_PREVENTIVA_MIN_H = 25.0


def relogio() -> datetime:
    """Instante atual (substituível nos testes)."""
    return datetime.now()


# ---------- códigos de equipamento nas atividades ----------

def normalizar(codigo: str) -> str:
    return re.sub(r"\s+", "", codigo or "").upper()


def codigos_da_atividade(texto: str | None) -> list[str]:
    """Extrai os códigos de equipamento do campo livre da atividade.

    "CM-07/08/09" -> ["CM-07", "CM-08", "CM-09"];  "ES-01 + CM-10" -> ["ES-01", "CM-10"].
    """
    if not texto:
        return []
    codigos, prefixo = [], ""
    for t in re.split(r"[/,;+&\s]+", texto.strip().upper()):
        if not t or t == "E":
            continue
        m = re.match(r"^([A-Z]+-?)(\d.*)$", t)
        if m:
            prefixo = m.group(1)
            codigos.append(t)
        elif re.fullmatch(r"\d+[A-Z]?", t) and prefixo:
            codigos.append(prefixo + t)
        else:
            codigos.append(t)
    return list(dict.fromkeys(codigos))


# ---------- janelas de tempo ----------

@dataclass
class Janela:
    inicio: datetime        # 00:00 do primeiro dia do período
    fim: datetime           # 00:00 do dia seguinte ao último dia do período
    corte: datetime         # até onde já "aconteceu" (fim do dia de referência ou agora)
    momento: datetime       # instante usado para o status atual do equipamento

    @property
    def horas_ate_corte(self) -> float:
        return max((self.corte - self.inicio).total_seconds() / 3600, 0.0)

    @property
    def horas_periodo(self) -> float:
        return (self.fim - self.inicio).total_seconds() / 3600


def montar_janela(inicio: date, fim: date, ref: date, agora: datetime | None = None) -> Janela:
    agora = agora or relogio()
    j_ini = datetime.combine(inicio, time.min)
    j_fim = datetime.combine(fim + timedelta(days=1), time.min)
    fim_ref = datetime.combine(ref + timedelta(days=1), time.min)
    corte = min(fim_ref, agora) if ref == agora.date() else fim_ref
    corte = min(max(corte, j_ini), j_fim)
    momento = agora if ref == agora.date() else datetime.combine(ref, time(12))
    return Janela(j_ini, j_fim, corte, momento)


def sobreposicao_h(a_ini: datetime, a_fim: datetime, b_ini: datetime, b_fim: datetime) -> float:
    s = (min(a_fim, b_fim) - max(a_ini, b_ini)).total_seconds() / 3600
    return max(s, 0.0)


def fim_efetivo(p: Parada, limite: datetime) -> datetime:
    """Parada em aberto vale até o limite informado (não sabemos quando termina)."""
    return p.fim if p.fim is not None else max(limite, p.inicio)


def parada_ativa(p: Parada, momento: datetime) -> bool:
    return p.inicio <= momento and (p.fim is None or p.fim > momento)


def janela_atividade(a: Atividade) -> tuple[datetime, datetime]:
    return (datetime.combine(a.inicio_planejado, time.min),
            datetime.combine(a.fim_planejado + timedelta(days=1), time.min))


# ---------- análise ----------

def _preventiva(e: Equipamento, paradas_futuras: list[Parada]) -> dict:
    programada = next((p.inicio for p in paradas_futuras if p.tipo == "preventiva"), None)
    info = {"estado": "sem_dados", "horimetro_atual": e.horimetro_atual, "horas_desde": None,
            "restante_h": None, "programada_para": programada}
    if not e.intervalo_preventiva_h or e.horimetro_atual is None or e.horimetro_ultima_preventiva is None:
        return info
    desde = e.horimetro_atual - e.horimetro_ultima_preventiva
    restante = e.intervalo_preventiva_h - desde
    margem = max(e.intervalo_preventiva_h * MARGEM_PREVENTIVA, MARGEM_PREVENTIVA_MIN_H)
    info.update(horas_desde=round(desde, 1), restante_h=round(restante, 1),
                estado="vencida" if restante <= 0 else "proxima" if restante <= margem else "ok")
    return info


def analisar_frota(
    equipamentos: list[Equipamento],
    atividades: list[Atividade],
    inicio: date,
    fim: date,
    ref: date | None = None,
    agora: datetime | None = None,
) -> dict:
    ref = ref or date.today()
    j = montar_janela(inicio, fim, ref, agora)

    sit = {a.id: calcular_situacao(a, ref) for a in atividades}
    por_codigo: dict[str, list[Atividade]] = {}
    for a in atividades:
        for c in codigos_da_atividade(a.equipamento):
            por_codigo.setdefault(c, []).append(a)

    cadastrados = {normalizar(e.codigo) for e in equipamentos}
    itens, conflitos = [], []

    for e in sorted(equipamentos, key=lambda x: (x.categoria or "", x.codigo)):
        ats = por_codigo.get(normalizar(e.codigo), [])
        no_periodo = [p for p in e.paradas if p.inicio < j.fim and fim_efetivo(p, j.corte) > j.inicio]

        h = {"corretiva": 0.0, "preventiva": 0.0, "operacional": 0.0}
        h_prog = 0.0                                    # manutenção programada após o corte
        n_corretivas = 0
        for p in no_periodo:
            fe = fim_efetivo(p, j.corte)
            h[p.tipo] = h.get(p.tipo, 0.0) + sobreposicao_h(p.inicio, fe, j.inicio, j.corte)
            if p.tipo in MANUTENCAO:
                h_prog += sobreposicao_h(p.inicio, fe, j.corte, j.fim)
            if p.tipo == "corretiva" and j.inicio <= p.inicio < j.corte:
                n_corretivas += 1

        h_cal = j.horas_ate_corte
        h_manut = h["corretiva"] + h["preventiva"]
        h_disp = max(h_cal - h_manut, 0.0)
        df = h_disp / h_cal if h_cal > 0 else None
        df_prev = (j.horas_periodo - h_manut - h_prog) / j.horas_periodo if j.horas_periodo else None

        regs = [r for r in e.registros_horas if inicio <= r.data <= min(fim, ref)]
        h_trab = sum(r.horas_trabalhadas for r in regs)
        uf = (h_trab / h_disp if h_disp > 0 else None) if regs else None

        ativa = next((p for p in e.paradas if parada_ativa(p, j.momento)), None)
        em_uso = [a for a in ats if sit[a.id].status != CONCLUIDA
                  and a.inicio_planejado <= j.momento.date() <= a.fim_planejado]
        if not e.ativo:
            status = "inativo"
        elif ativa:
            status = "manutencao" if ativa.tipo in MANUTENCAO else "parado"
        elif em_uso:
            status = "operando"
        else:
            status = "disponivel"

        futuras = [p for p in e.paradas if p.inicio >= j.momento]
        prev = _preventiva(e, futuras)

        # Conflitos: atividade ainda não concluída x parada que cruza a janela planejada dela.
        for a in ats:
            s = sit[a.id]
            if s.status == CONCLUIDA:
                continue
            a_ini, a_fim = janela_atividade(a)
            n_eq = max(len(codigos_da_atividade(a.equipamento)), 1)
            for p in e.paradas:
                fe = fim_efetivo(p, max(j.corte, j.momento))
                horas = sobreposicao_h(p.inicio, fe, a_ini, a_fim)
                if horas <= 0:
                    continue
                janela_h = (a_fim - a_ini).total_seconds() / 3600
                perda = horas / (janela_h * n_eq)       # fração da capacidade planejada da atividade
                conflitos.append({
                    "atividade_id": a.id, "codigo_atividade": a.codigo, "descricao": a.descricao,
                    "frente": a.frente, "tipo_atividade": a.tipo, "unidade": a.unidade,
                    "inicio_planejado": a.inicio_planejado, "fim_planejado": a.fim_planejado,
                    "status_atividade": s.status, "equipamento_id": e.id, "equipamento": e.codigo,
                    "equipamentos_na_atividade": n_eq, "parada_id": p.id, "tipo_parada": p.tipo,
                    "motivo": p.motivo, "parada_inicio": p.inicio, "parada_fim": p.fim,
                    "em_aberto": p.fim is None, "programada": p.inicio > j.momento,
                    "horas_sobrepostas": round(horas, 1), "perda_capacidade": round(perda, 4),
                    "producao_em_risco": round((a.qtd_planejada or 0) * perda, 2),
                })

        itens.append({
            "id": e.id, "codigo": e.codigo, "descricao": e.descricao, "categoria": e.categoria,
            "frente": e.frente, "ativo": e.ativo, "meta_df": e.meta_df, "observacoes": e.observacoes,
            "intervalo_preventiva_h": e.intervalo_preventiva_h,
            "horimetro_ultima_preventiva": e.horimetro_ultima_preventiva,
            "status": status, "status_rotulo": STATUS_EQ[status],
            "parada_atual": _parada_dict(ativa) if ativa else None,
            "horas_calendario": round(h_cal, 1),
            "horas_corretiva": round(h["corretiva"], 1),
            "horas_preventiva": round(h["preventiva"], 1),
            "horas_operacional": round(h["operacional"], 1),
            "horas_manutencao_programada": round(h_prog, 1),
            "horas_disponiveis": round(h_disp, 1),
            "horas_trabalhadas": round(h_trab, 1) if regs else None,
            "df": round(df, 4) if df is not None else None,
            "df_prevista": round(df_prev, 4) if df_prev is not None else None,
            "uf": round(uf, 4) if uf is not None else None,
            "rendimento": round(df * uf, 4) if df is not None and uf is not None else None,
            "corretivas": n_corretivas,
            "mttr_h": round(h["corretiva"] / n_corretivas, 1) if n_corretivas else None,
            "preventiva": prev,
            "atividades": [{"id": a.id, "codigo": a.codigo, "descricao": a.descricao, "frente": a.frente,
                            "inicio_planejado": a.inicio_planejado, "fim_planejado": a.fim_planejado,
                            "status": sit[a.id].status} for a in ats],
            "paradas": [_parada_dict(p) for p in no_periodo],
        })

    ativos = [i for i in itens if i["ativo"]]
    dfs = [i["df"] for i in ativos if i["df"] is not None]
    dfp = [i["df_prevista"] for i in ativos if i["df_prevista"] is not None]
    ufs = [i["uf"] for i in ativos if i["uf"] is not None]
    contagem = {k: sum(i["status"] == k for i in itens) for k in STATUS_EQ}

    categorias: dict[str, list] = {}
    for i in ativos:
        categorias.setdefault(i["categoria"] or "Sem categoria", []).append(i)
    por_categoria = []
    for nome, lst in sorted(categorias.items()):
        d = [i["df"] for i in lst if i["df"] is not None]
        u = [i["uf"] for i in lst if i["uf"] is not None]
        por_categoria.append({
            "categoria": nome, "equipamentos": len(lst),
            "em_manutencao": sum(i["status"] == "manutencao" for i in lst),
            "df": round(sum(d) / len(d), 4) if d else None,
            "uf": round(sum(u) / len(u), 4) if u else None,
        })

    nao_cadastrados = sorted(c for c in por_codigo if c not in cadastrados)
    conflitos.sort(key=lambda c: (c["programada"], -c["perda_capacidade"]))

    return {
        "inicio": inicio, "fim": fim, "data_referencia": ref,
        "resumo": {
            "total": len(itens), "ativos": len(ativos), "contagem": contagem,
            "df_media": round(sum(dfs) / len(dfs), 4) if dfs else None,
            "df_prevista": round(sum(dfp) / len(dfp), 4) if dfp else None,
            "uf_media": round(sum(ufs) / len(ufs), 4) if ufs else None,
            "horas_corretiva": round(sum(i["horas_corretiva"] for i in itens), 1),
            "horas_preventiva": round(sum(i["horas_preventiva"] for i in itens), 1),
            "preventivas_vencidas": sum(i["preventiva"]["estado"] == "vencida" for i in ativos),
            "preventivas_proximas": sum(i["preventiva"]["estado"] == "proxima" for i in ativos),
            "abaixo_meta": sum(i["df"] is not None and i["df"] < i["meta_df"] for i in ativos),
            "conflitos": len(conflitos),
            "atividades_afetadas": len({c["atividade_id"] for c in conflitos}),
        },
        "por_categoria": por_categoria,
        "equipamentos": itens,
        "conflitos": conflitos,
        "nao_cadastrados": nao_cadastrados,
    }


def _parada_dict(p: Parada) -> dict:
    return {"id": p.id, "equipamento_id": p.equipamento_id, "tipo": p.tipo, "inicio": p.inicio, "fim": p.fim,
            "motivo": p.motivo, "horimetro": p.horimetro}
