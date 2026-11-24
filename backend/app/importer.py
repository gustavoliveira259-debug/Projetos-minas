"""Leitura de planilhas de planejamento (.xlsx / .xlsm / .csv).

Os cabeçalhos são reconhecidos de forma tolerante: maiúsculas, acentos, espaços e
pontuação são ignorados, e vários sinônimos usados no dia a dia da mina são aceitos
(ex.: "Frente de Lavra", "Local", "Cava" -> frente).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from openpyxl import load_workbook

ALIASES: dict[str, list[str]] = {
    "codigo": ["codigo", "cod", "id", "idatividade", "item", "codatividade", "wbs", "edt"],
    "descricao": ["descricao", "atividade", "tarefa", "nome", "descricaodaatividade", "servico"],
    "tipo": ["tipo", "operacao", "processo", "categoria", "tipodeatividade", "disciplina"],
    "frente": ["frente", "frentedelavra", "frentedetrabalho", "local", "cava", "banco", "area", "mina", "pit"],
    "equipamento": ["equipamento", "equip", "frota", "maquina", "tag", "equipamentos"],
    "responsavel": ["responsavel", "encarregado", "supervisor", "lider"],
    "unidade": ["unidade", "un", "und", "unid", "um"],
    "qtd_planejada": ["qtdplanejada", "quantidadeplanejada", "planejado", "qtdplan", "quantidade", "qtd",
                      "volume", "massa", "meta", "qtdeplanejada", "previsto", "qtdprevista"],
    "qtd_realizada": ["qtdrealizada", "quantidaderealizada", "realizado", "qtdreal", "qtderealizada", "executado"],
    "inicio_planejado": ["inicioplanejado", "inicio", "datainicio", "datainicial", "inicioprevisto",
                         "datadeinicio", "iniplan", "inicioplan"],
    "fim_planejado": ["fimplanejado", "fim", "termino", "terminoplanejado", "datafim", "datafinal", "fimprevisto",
                      "datadetermino", "terminoprevisto", "fimplan"],
    "duracao": ["duracao", "duracaodias", "dias", "prazo", "prazodias"],
    "inicio_real": ["inicioreal", "datainicioreal", "inicioexecutado"],
    "fim_real": ["fimreal", "terminoreal", "datafimreal", "conclusao", "dataconclusao"],
    "observacoes": ["observacoes", "observacao", "obs", "comentarios", "comentario", "notas"],
}

_INDICE = {alias: campo for campo, lst in ALIASES.items() for alias in lst}


def normalizar(texto) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def mapear_cabecalho(cabecalho: list) -> dict[int, str]:
    mapa: dict[int, str] = {}
    usados = set()
    for i, col in enumerate(cabecalho):
        campo = _INDICE.get(normalizar(col))
        if campo and campo not in usados:
            mapa[i] = campo
            usados.add(campo)
    return mapa


# ---------- conversões ----------

_EXCEL_EPOCH = date(1899, 12, 30)


def para_data(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        if 1 < v < 100000:  # número de série do Excel
            return _EXCEL_EPOCH + timedelta(days=int(v))
        raise ValueError(f"data inválida: {v}")
    s = str(v).strip().split(" ")[0].split("T")[0]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {v}")


def para_numero(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise ValueError(f"número inválido: {v}")
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v).strip())
    if not s:
        return None
    if "," in s:                                   # padrão brasileiro: 1.234,5
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):  # 1.234.567 = milhar
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"número inválido: {v}")


def _texto(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


# ---------- leitura ----------

@dataclass
class LinhaImportada:
    linha: int
    dados: dict
    qtd_realizada: float | None = None
    erros: list[str] = field(default_factory=list)


@dataclass
class ResultadoLeitura:
    aba: str | None
    linha_cabecalho: int
    colunas_reconhecidas: dict[str, str]
    colunas_ignoradas: list[str]
    linhas: list[LinhaImportada]

    @property
    def validas(self):
        return [l for l in self.linhas if not l.erros]

    @property
    def invalidas(self):
        return [l for l in self.linhas if l.erros]


def _linhas_planilha(conteudo: bytes, nome: str) -> tuple[str | None, list[list]]:
    """Retorna (nome_da_aba, linhas). Em .xlsx escolhe a aba que parece um planejamento."""
    if nome.lower().endswith(".csv"):
        texto = None
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                texto = conteudo.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t") if texto.strip() else csv.excel
        return None, [row for row in csv.reader(io.StringIO(texto), dialeto)]

    wb = load_workbook(io.BytesIO(conteudo), data_only=True, read_only=True)
    melhor = (None, [], -1)
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        pontos = max((len(mapear_cabecalho(r)) for r in rows[:15]), default=0)
        if pontos > melhor[2]:
            melhor = (ws.title, rows, pontos)
    wb.close()
    return melhor[0], melhor[1]


def ler_planilha(conteudo: bytes, nome: str) -> ResultadoLeitura:
    aba, rows = _linhas_planilha(conteudo, nome)

    # O cabeçalho é a linha (entre as 15 primeiras) com mais colunas reconhecidas.
    idx_cab, mapa = 0, {}
    for i, r in enumerate(rows[:15]):
        m = mapear_cabecalho(r)
        if len(m) > len(mapa):
            idx_cab, mapa = i, m
    campos = set(mapa.values())
    faltando = [c for c in ("descricao", "inicio_planejado") if c not in campos]
    if "fim_planejado" not in campos and "duracao" not in campos:
        faltando.append("fim_planejado (ou duração)")
    if faltando:
        raise ValueError(
            "Não encontrei as colunas obrigatórias: " + ", ".join(faltando)
            + ". Baixe o modelo de planilha para ver os nomes aceitos."
        )

    cab = rows[idx_cab]
    reconhecidas = {str(cab[i]).strip(): c for i, c in mapa.items()}
    ignoradas = [str(c).strip() for i, c in enumerate(cab) if i not in mapa and c not in (None, "")]

    linhas: list[LinhaImportada] = []
    for n, r in enumerate(rows[idx_cab + 1:], start=idx_cab + 2):
        if not r or all(v in (None, "") for v in r):
            continue
        bruto = {campo: (r[i] if i < len(r) else None) for i, campo in mapa.items()}
        linhas.append(_converter_linha(n, bruto))
    return ResultadoLeitura(aba, idx_cab + 1, reconhecidas, ignoradas, linhas)


def _converter_linha(n: int, bruto: dict) -> LinhaImportada:
    erros: list[str] = []
    d: dict = {}

    for c in ("codigo", "descricao", "tipo", "frente", "equipamento", "responsavel", "unidade", "observacoes"):
        if c in bruto:
            d[c] = _texto(bruto[c])

    for c in ("inicio_planejado", "fim_planejado", "inicio_real", "fim_real"):
        if c not in bruto and c not in ("inicio_planejado", "fim_planejado"):
            continue  # coluna ausente: não mexe no valor existente
        try:
            d[c] = para_data(bruto.get(c))
        except ValueError as e:
            erros.append(f"{c}: {e}")
            d[c] = None

    qtd_real = None
    for c in ("qtd_planejada", "qtd_realizada", "duracao"):
        try:
            v = para_numero(bruto.get(c))
        except ValueError as e:
            erros.append(f"{c}: {e}")
            v = None
        if c == "qtd_planejada":
            if c in bruto:
                d[c] = v or 0.0
            if v is not None and v < 0:
                erros.append("qtd_planejada não pode ser negativa")
        elif c == "qtd_realizada":
            qtd_real = v
        elif v and not d.get("fim_planejado") and d.get("inicio_planejado"):
            d["fim_planejado"] = d["inicio_planejado"] + timedelta(days=max(int(round(v)) - 1, 0))

    if not d.get("descricao"):
        erros.append("descrição vazia")
    if not d.get("inicio_planejado"):
        erros.append("início planejado vazio")
    if not d.get("fim_planejado"):
        erros.append("fim planejado vazio")
    if d.get("inicio_planejado") and d.get("fim_planejado") and d["fim_planejado"] < d["inicio_planejado"]:
        erros.append("fim planejado anterior ao início")
    if "unidade" in d and not d["unidade"]:
        del d["unidade"]  # usa o padrão do cadastro ("t") ou mantém o atual

    return LinhaImportada(linha=n, dados=d, qtd_realizada=qtd_real, erros=erros)
