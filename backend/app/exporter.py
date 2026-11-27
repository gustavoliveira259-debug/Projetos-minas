"""Geração de planilhas Excel (exportação e modelo de importação)."""
from __future__ import annotations

import io
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Atividade
from .status import calcular_situacao, indicadores, semana_iso

CAB_FILL = PatternFill("solid", fgColor="1F3A5F")
CAB_FONT = Font(bold=True, color="FFFFFF")
STATUS_FILL = {
    "atrasada": "F8D7D7",
    "adiantada": "E0DCF7",
    "concluida": "D6F0D6",
    "no_prazo": "DCE9F9",
    "nao_iniciada": "EEEEEE",
}
FMT_DATA = "DD/MM/YYYY"
FMT_NUM = "#,##0.00"
FMT_PCT = "0.0%"


def _tabela(ws, cabecalho: list[str], linhas: list[list], formatos: dict[int, str] | None = None):
    ws.append(cabecalho)
    for c in ws[1]:
        c.fill, c.font = CAB_FILL, CAB_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for row in linhas:
        ws.append(row)
    formatos = formatos or {}
    for col_idx, fmt in formatos.items():
        for (cell,) in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
            cell.number_format = fmt
    for i, titulo in enumerate(cabecalho, start=1):
        largura = max([len(str(titulo))] + [len(str(r[i - 1])) for r in linhas[:300] if r[i - 1] is not None])
        ws.column_dimensions[get_column_letter(i)].width = min(max(largura + 2, 10), 50)
    ws.freeze_panes = "A2"
    if linhas:
        ws.auto_filter.ref = ws.dimensions


def _aba_por_frente(ws, atividades: list[Atividade], ref: date) -> None:
    """Uma linha por frente + tipo (+ unidade): contagens e produção planejada × realizada.

    Ao fim de cada frente há uma linha de total só com as contagens (unidades diferentes não se somam).
    """
    grupos: dict[tuple, dict] = {}
    for a in atividades:
        s = calcular_situacao(a, ref)
        chave = (a.frente or "Sem frente", a.tipo or "Sem tipo", a.unidade or "")
        g = grupos.setdefault(chave, {"total": 0, "concluidas": 0, "atrasadas": 0, "plan": 0.0, "real": 0.0})
        g["total"] += 1
        g["concluidas"] += s.status == "concluida"
        g["atrasadas"] += s.status == "atrasada"
        if a.qtd_planejada:
            g["plan"] += a.qtd_planejada
            g["real"] += s.qtd_realizada

    cab = ["Frente", "Tipo", "Data", "Atividades totais", "Concluídas", "Atrasadas",
           "Unidade", "Planejado", "Realizado", "Atingimento"]
    linhas, linhas_total = [], []
    frentes = sorted({k[0] for k in grupos})
    for frente in frentes:
        itens = sorted((k, g) for k, g in grupos.items() if k[0] == frente)
        for (_, tipo, un), g in itens:
            tem_qtd = g["plan"] > 0
            linhas.append([frente, tipo, ref, g["total"], g["concluidas"], g["atrasadas"],
                           un if tem_qtd else None,
                           round(g["plan"], 2) if tem_qtd else None,
                           round(g["real"], 2) if tem_qtd else None,
                           round(g["real"] / g["plan"], 4) if tem_qtd else None])
        if len(itens) > 1:
            linhas.append([f"Total {frente}", None, ref, *(sum(g[k] for _, g in itens)
                           for k in ("total", "concluidas", "atrasadas")), None, None, None, None])
            linhas_total.append(len(linhas) + 1)
    if len(frentes) > 1:
        linhas.append(["Total geral", None, ref, *(sum(g[k] for g in grupos.values())
                       for k in ("total", "concluidas", "atrasadas")), None, None, None, None])
        linhas_total.append(len(linhas) + 1)

    _tabela(ws, cab, linhas, {3: FMT_DATA, 8: FMT_NUM, 9: FMT_NUM, 10: FMT_PCT})
    for r in linhas_total:
        for c in ws[r]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="E8EDF3")


FMT_DATA_HORA = "DD/MM/YYYY HH:MM"
EQ_FILL = {"manutencao": "F8D7D7", "parado": "FCEFD0", "operando": "DCE9F9", "disponivel": "D6F0D6", "inativo": "EEEEEE"}


def _abas_frota(wb, frota: dict) -> list[str]:
    """Abas Equipamentos, Paradas e Conflitos (resultado de frota.analisar_frota)."""
    ws = wb.create_sheet("Equipamentos")
    cab = ["Código", "Descrição", "Categoria", "Frente", "Situação", "DF", "Meta DF", "DF prevista", "UF",
           "Horas calendário", "Horas corretiva", "Horas preventiva", "Horas operacional", "Manut. programada (h)",
           "Horas trabalhadas", "Nº corretivas", "MTTR (h)", "Horímetro", "Preventiva", "Faltam (h)",
           "Atividades no período"]
    rotulo_prev = {"vencida": "Vencida", "proxima": "Próxima", "ok": "Em dia", "sem_dados": "—"}
    linhas, sts = [], []
    for e in frota["equipamentos"]:
        pv = e["preventiva"]
        linhas.append([e["codigo"], e["descricao"], e["categoria"], e["frente"], e["status_rotulo"], e["df"],
                       e["meta_df"], e["df_prevista"], e["uf"], e["horas_calendario"], e["horas_corretiva"],
                       e["horas_preventiva"], e["horas_operacional"], e["horas_manutencao_programada"],
                       e["horas_trabalhadas"], e["corretivas"], e["mttr_h"], pv["horimetro_atual"],
                       rotulo_prev[pv["estado"]], pv["restante_h"], len(e["atividades"])])
        sts.append(e["status"])
    _tabela(ws, cab, linhas, {6: FMT_PCT, 7: FMT_PCT, 8: FMT_PCT, 9: FMT_PCT})
    for r, st in enumerate(sts, start=2):
        ws.cell(r, 5).fill = PatternFill("solid", fgColor=EQ_FILL[st])

    ws2 = wb.create_sheet("Paradas")
    paradas = [[e["codigo"], e["categoria"], p["tipo"].capitalize(), p["inicio"], p["fim"],
                round(((p["fim"] - p["inicio"]).total_seconds() / 3600), 1) if p["fim"] else None,
                "Em aberto" if p["fim"] is None else None, p["motivo"], p["horimetro"]]
               for e in frota["equipamentos"] for p in e["paradas"]]
    _tabela(ws2, ["Equipamento", "Categoria", "Tipo", "Início", "Fim", "Duração (h)", "Situação", "Motivo",
                  "Horímetro"], paradas, {4: FMT_DATA_HORA, 5: FMT_DATA_HORA, 6: FMT_NUM})

    ws3 = wb.create_sheet("Conflitos")
    _tabela(ws3, ["Atividade", "Descrição", "Frente", "Início planejado", "Fim planejado", "Equipamento",
                  "Tipo de parada", "Início parada", "Fim parada", "Horas sobrepostas", "Perda de capacidade",
                  "Produção em risco", "Unidade", "Programada"],
            [[c["codigo_atividade"], c["descricao"], c["frente"], c["inicio_planejado"], c["fim_planejado"],
              c["equipamento"], c["tipo_parada"].capitalize(), c["parada_inicio"], c["parada_fim"],
              c["horas_sobrepostas"], c["perda_capacidade"], c["producao_em_risco"], c["unidade"],
              "Sim" if c["programada"] else "Não"] for c in frota["conflitos"]],
            {4: FMT_DATA, 5: FMT_DATA, 8: FMT_DATA_HORA, 9: FMT_DATA_HORA, 10: FMT_NUM, 11: FMT_PCT, 12: FMT_NUM})
    return ["Equipamentos", "Paradas", "Conflitos"]


def exportar_excel(atividades: list[Atividade], ref: date | None = None, frota: dict | None = None) -> bytes:
    ref = ref or date.today()
    wb = Workbook()

    # --- Atividades ---
    ws = wb.active
    ws.title = "Atividades"
    cab = ["ID", "Código", "Atividade", "Tipo", "Frente", "Equipamento", "Responsável", "Unidade",
           "Qtd planejada", "Qtd realizada", "Saldo", "Qtd esperada até ref.", "Projeção no ritmo atual",
           "Impacto na meta", "Início planejado", "Fim planejado", "Início real", "Fim real", "Semana",
           "Progresso real", "Progresso esperado", "Desvio (p.p.)", "Situação", "Dias de atraso", "Observações",
           "Depende de"]
    linhas, status_linha = [], []
    for a in atividades:
        s = calcular_situacao(a, ref)
        linhas.append([a.id, a.codigo, a.descricao, a.tipo, a.frente, a.equipamento, a.responsavel, a.unidade,
                       a.qtd_planejada, s.qtd_realizada, s.saldo, s.qtd_esperada, s.projecao, s.impacto_meta,
                       a.inicio_planejado, a.fim_planejado, a.inicio_real, a.fim_real,
                       semana_iso(a.inicio_planejado), s.progresso_real, s.progresso_esperado, s.desvio,
                       s.rotulo, s.dias_atraso, a.observacoes,
                       ", ".join(p.codigo or p.descricao for p in a.predecessoras) or None])
        status_linha.append(s.status)
    fmts = {i: FMT_NUM for i in range(9, 15)} | {i: FMT_DATA for i in range(15, 19)} | {20: FMT_PCT, 21: FMT_PCT, 22: FMT_PCT}
    _tabela(ws, cab, linhas, fmts)
    for r, st in enumerate(status_linha, start=2):
        ws.cell(r, 23).fill = PatternFill("solid", fgColor=STATUS_FILL[st])

    # --- Apontamentos ---
    ws2 = wb.create_sheet("Apontamentos")
    ap = [[p.id, a.id, a.codigo, a.descricao, a.frente, a.tipo, a.unidade, p.data, p.quantidade, p.observacao]
          for a in atividades for p in a.apontamentos]
    _tabela(ws2, ["ID", "ID atividade", "Código", "Atividade", "Frente", "Tipo", "Unidade", "Data",
                  "Quantidade", "Observação"], ap, {8: FMT_DATA, 9: FMT_NUM})

    # --- Indicadores ---
    ind = indicadores(atividades, ref)
    ws3 = wb.create_sheet("Indicadores")
    _tabela(ws3, ["Tipo", "Unidade", "Atividades", "Planejado", "Esperado até ref.", "Realizado", "Projeção",
                  "Impacto na meta", "Atingimento", "Aderência até ref."],
            [[p["tipo"], p["unidade"], p["atividades"], p["planejado"], p["esperado_ate_ref"], p["realizado"],
              p["projecao"], p["impacto_meta"], p["atingimento"], p["aderencia_ate_ref"]] for p in ind["producao"]],
            {4: FMT_NUM, 5: FMT_NUM, 6: FMT_NUM, 7: FMT_NUM, 8: FMT_NUM, 9: FMT_PCT, 10: FMT_PCT})

    # --- Resumo ---
    ws4 = wb.create_sheet("Resumo")
    c = ind["contagem"]
    _tabela(ws4, ["Indicador", "Valor"], [
        ["Data de referência", ref],
        ["Total de atividades", ind["total"]],
        ["Aderência ao plano", ind["aderencia"]],
        ["Concluídas", c["concluida"]],
        ["No prazo", c["no_prazo"]],
        ["Adiantadas", c["adiantada"]],
        ["Atrasadas", c["atrasada"]],
        ["Não iniciadas", c["nao_iniciada"]],
        ["Tolerância de desvio", ind["tolerancia"]],
    ])
    ws4["B2"].number_format = FMT_DATA
    ws4["B4"].number_format = FMT_PCT
    ws4["B10"].number_format = FMT_PCT

    # --- Por frente ---
    _aba_por_frente(wb.create_sheet("Por frente"), atividades, ref)

    abas_frota = _abas_frota(wb, frota) if frota and frota["equipamentos"] else []

    wb._sheets = [wb[n] for n in ("Resumo", "Por frente", "Atividades", "Apontamentos", "Indicadores", *abas_frota)]
    wb.active = 0

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def modelo_importacao() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Planejamento"
    seg = date.today() - timedelta(days=date.today().weekday())
    cab = ["Código", "Atividade", "Tipo", "Frente", "Equipamento", "Responsável", "Unidade",
           "Qtd Planejada", "Qtd Realizada", "Início Planejado", "Fim Planejado", "Observações"]
    exemplos = [
        ["PF-001", "Perfuração banco 820", "Perfuração", "Cava Norte", "PF-03", "João", "m", 1200, None,
         seg, seg + timedelta(days=2), "Malha 4x5"],
        ["DM-001", "Desmonte banco 820", "Desmonte", "Cava Norte", None, "Maria", "t", 45000, None,
         seg + timedelta(days=3), seg + timedelta(days=3), None],
        ["CG-001", "Carregamento e transporte minério", "Carregamento", "Cava Norte", "ES-01", "Carlos", "t",
         38000, None, seg + timedelta(days=3), seg + timedelta(days=6), "Destino: britagem primária"],
    ]
    _tabela(ws, cab, exemplos, {8: FMT_NUM, 9: FMT_NUM, 10: FMT_DATA, 11: FMT_DATA})

    ajuda = wb.create_sheet("Instruções")
    for linha in [
        ["Como preencher"],
        ["Obrigatórias: Atividade, Início Planejado e Fim Planejado (ou Duração em dias)."],
        ["Datas no formato DD/MM/AAAA ou como data do Excel."],
        ["Qtd Realizada (opcional) é registrada como apontamento de produção."],
        ["Linhas com Código já existente no sistema são atualizadas no modo 'mesclar'."],
        ["Nomes de coluna alternativos também são aceitos (ex.: Frente de Lavra, Local, Término, Volume)."],
    ]:
        ajuda.append(linha)
    ajuda["A1"].font = Font(bold=True, size=13)
    ajuda.column_dimensions["A"].width = 100

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
