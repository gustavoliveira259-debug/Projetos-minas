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
    stmt = select(Atividade).options(selectinload(Atividade.apontamentos))
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


def atividade_dict(a: Atividade, ref: date | None = None) -> dict:
    d = {c: getattr(a, c) for c in CAMPOS}
    d.update(id=a.id, qtd_realizada=a.qtd_realizada, criado_em=a.criado_em, atualizado_em=a.atualizado_em,
             situacao=calcular_situacao(a, ref).as_dict())
    return d
