"""Consultas compartilhadas entre as rotas, exportação e Power BI."""
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .models import Atividade
from .status import calcular_situacao


def listar_atividades(
    db: Session,
    inicio: date | None = None,
    fim: date | None = None,
    frente: str | None = None,
    tipo: str | None = None,
    busca: str | None = None,
    incluir_pendentes: bool = True,
) -> list[Atividade]:
    """Atividades cujo período planejado cruza [inicio, fim] (ambos opcionais).

    Com ``incluir_pendentes``, atividades de períodos anteriores que ainda não foram
    concluídas (ou que foram concluídas dentro do período) também entram: um atraso
    da semana passada continua sendo um problema da semana atual.
    """
    stmt = select(Atividade).options(
        selectinload(Atividade.apontamentos),
        selectinload(Atividade.predecessoras),
        selectinload(Atividade.sucessoras),
    )
    if inicio and incluir_pendentes:
        stmt = stmt.where(or_(Atividade.fim_planejado >= inicio, Atividade.fim_real.is_(None),
                              Atividade.fim_real >= inicio))
    elif inicio:
        stmt = stmt.where(Atividade.fim_planejado >= inicio)
    if fim:
        stmt = stmt.where(Atividade.inicio_planejado <= fim)
    if frente:
        stmt = stmt.where(Atividade.frente == frente)
    if tipo:
        stmt = stmt.where(Atividade.tipo == tipo)
    if busca:
        like = f"%{busca}%"
        stmt = stmt.where(or_(
            Atividade.descricao.ilike(like), Atividade.codigo.ilike(like),
            Atividade.equipamento.ilike(like), Atividade.responsavel.ilike(like),
        ))
    stmt = stmt.order_by(Atividade.frente, Atividade.inicio_planejado, Atividade.id)
    itens = list(db.scalars(stmt))
    if inicio and incluir_pendentes:
        itens = [a for a in itens if a.fim_planejado >= inicio or _pendente_em(a, inicio)]
    return itens


def _pendente_em(a: Atividade, inicio: date) -> bool:
    """Atividade anterior ao período que segue aberta, ou que só foi concluída dentro dele."""
    s = calcular_situacao(a, inicio)
    if s.status != "concluida":
        return True
    return (s.data_conclusao or inicio) >= inicio


CAMPOS = [
    "codigo", "descricao", "tipo", "frente", "equipamento", "responsavel", "unidade", "qtd_planejada",
    "inicio_planejado", "fim_planejado", "inicio_real", "fim_real", "progresso_manual", "observacoes",
]


def atividade_ref(a: Atividade) -> dict:
    return {"id": a.id, "codigo": a.codigo, "descricao": a.descricao,
            "inicio_planejado": a.inicio_planejado, "fim_planejado": a.fim_planejado}


def atividade_dict(a: Atividade, ref: date | None = None) -> dict:
    d = {c: getattr(a, c) for c in CAMPOS}
    d.update(id=a.id, qtd_realizada=a.qtd_realizada, criado_em=a.criado_em, atualizado_em=a.atualizado_em,
             situacao=calcular_situacao(a, ref).as_dict(),
             predecessoras=[atividade_ref(p) for p in a.predecessoras],
             sucessoras=[atividade_ref(s) for s in a.sucessoras])
    return d


# ---------- Dependências (término → início) ----------
# Uma atividade dependente pode começar no mesmo dia em que a predecessora termina
# (ex.: desmonte pela manhã, carregamento à tarde), mas nunca antes.

def nome_curto(a: Atividade) -> str:
    return a.codigo or a.descricao


def depende_de(a: Atividade, alvo: Atividade) -> bool:
    """True se ``a`` depende (direta ou indiretamente) de ``alvo``."""
    vistos, pilha = set(), list(a.predecessoras)
    while pilha:
        p = pilha.pop()
        if p.id == alvo.id:
            return True
        if p.id not in vistos:
            vistos.add(p.id)
            pilha.extend(p.predecessoras)
    return False


def validar_predecessoras(a: Atividade, predecessoras: list[Atividade]) -> None:
    """Levanta ValueError para autodependência ou ciclo (A depende de B que depende de A)."""
    for p in predecessoras:
        if p.id == a.id:
            raise ValueError("Uma atividade não pode depender dela mesma.")
        if a.id is not None and depende_de(p, a):
            raise ValueError(f"{nome_curto(p)} já depende de {nome_curto(a)}; a dependência criaria um ciclo.")


def validar_inicio(inicio: date, predecessoras: list[Atividade]) -> None:
    """A atividade não pode começar antes do fim de nenhuma predecessora."""
    if not predecessoras:
        return
    limite = max(predecessoras, key=lambda p: p.fim_planejado)
    if inicio < limite.fim_planejado:
        raise ValueError(
            f"Esta atividade depende de {nome_curto(limite)}, que termina em "
            f"{limite.fim_planejado:%d/%m/%Y}; o início planejado não pode ser anterior a essa data."
        )


def empurrar_dependentes(a: Atividade) -> list[Atividade]:
    """Adia (mantendo a duração) as dependentes que passariam a começar antes do fim de ``a``,
    em cascata. Só empurra para frente: adiantar a predecessora não puxa as dependentes."""
    movidas: dict[int, Atividade] = {}
    fila = [a]
    while fila:
        p = fila.pop(0)
        for s in p.sucessoras:
            if s.inicio_planejado < p.fim_planejado:
                delta = p.fim_planejado - s.inicio_planejado
                s.inicio_planejado += delta
                s.fim_planejado += delta
                movidas[s.id] = s
                fila.append(s)
    return sorted(movidas.values(), key=lambda x: (x.inicio_planejado, x.id))
