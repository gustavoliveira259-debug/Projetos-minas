from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Apontamento, Atividade
from ..schemas import (
    ApontamentoCreate, ApontamentoOut, AtividadeCreate, AtividadeOut, AtividadeUpdate, validar_datas,
)
from ..services import CAMPOS, atividade_dict, listar_atividades
from ..status import indicadores

router = APIRouter(prefix="/api", tags=["atividades"])


def _obter(db: Session, atividade_id: int) -> Atividade:
    a = db.get(Atividade, atividade_id)
    if not a:
        raise HTTPException(404, "Atividade não encontrada.")
    return a


@router.get("/atividades", response_model=list[AtividadeOut])
def listar(
    inicio: date | None = None,
    fim: date | None = None,
    frente: str | None = None,
    tipo: str | None = None,
    status: str | None = Query(None, description="nao_iniciada, no_prazo, atrasada, adiantada, concluida"),
    busca: str | None = None,
    data_ref: date | None = Query(None, description="Data de referência para o cálculo da situação (padrão: hoje)"),
    db: Session = Depends(get_db),
):
    itens = [atividade_dict(a, data_ref) for a in listar_atividades(db, inicio, fim, frente, tipo, busca)]
    if status:
        itens = [i for i in itens if i["situacao"]["status"] == status]
    return itens


@router.get("/atividades/filtros")
def filtros(db: Session = Depends(get_db)):
    """Valores distintos para preencher os filtros e autocompletar formulários."""
    def distintos(col):
        return sorted(v for v in db.scalars(select(col).distinct()) if v)
    return {
        "frentes": distintos(Atividade.frente),
        "tipos": distintos(Atividade.tipo),
        "equipamentos": distintos(Atividade.equipamento),
        "responsaveis": distintos(Atividade.responsavel),
        "unidades": distintos(Atividade.unidade),
    }


@router.post("/atividades", response_model=AtividadeOut, status_code=201)
def criar(dados: AtividadeCreate, db: Session = Depends(get_db)):
    a = Atividade(**dados.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return atividade_dict(a)


@router.get("/atividades/{atividade_id}", response_model=AtividadeOut)
def obter(atividade_id: int, data_ref: date | None = None, db: Session = Depends(get_db)):
    return atividade_dict(_obter(db, atividade_id), data_ref)


@router.patch("/atividades/{atividade_id}", response_model=AtividadeOut)
def atualizar(atividade_id: int, dados: AtividadeUpdate, db: Session = Depends(get_db)):
    a = _obter(db, atividade_id)
    mudancas = dados.model_dump(exclude_unset=True)
    if "descricao" in mudancas and not mudancas["descricao"]:
        raise HTTPException(422, "A descrição é obrigatória.")
    final = {c: getattr(a, c) for c in CAMPOS} | mudancas
    try:
        validar_datas(final)
    except ValueError as e:
        raise HTTPException(422, str(e))
    for k, v in mudancas.items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return atividade_dict(a)


@router.delete("/atividades/{atividade_id}", status_code=204)
def excluir(atividade_id: int, db: Session = Depends(get_db)):
    db.delete(_obter(db, atividade_id))
    db.commit()


# ---------- Andamento (apontamentos de produção) ----------

@router.get("/atividades/{atividade_id}/apontamentos", response_model=list[ApontamentoOut])
def listar_apontamentos(atividade_id: int, db: Session = Depends(get_db)):
    return _obter(db, atividade_id).apontamentos


@router.post("/atividades/{atividade_id}/apontamentos", response_model=AtividadeOut, status_code=201)
def apontar(atividade_id: int, dados: ApontamentoCreate, db: Session = Depends(get_db)):
    a = _obter(db, atividade_id)
    if dados.quantidade > 0 or dados.observacao:
        a.apontamentos.append(Apontamento(data=dados.data, quantidade=dados.quantidade, observacao=dados.observacao))
    if a.inicio_real is None and (dados.quantidade > 0 or dados.concluir):
        a.inicio_real = dados.data
    if dados.concluir:
        a.fim_real = max(dados.data, a.inicio_real or dados.data)
    db.commit()
    db.refresh(a)
    return atividade_dict(a)


@router.delete("/apontamentos/{apontamento_id}", status_code=204)
def excluir_apontamento(apontamento_id: int, db: Session = Depends(get_db)):
    ap = db.get(Apontamento, apontamento_id)
    if not ap:
        raise HTTPException(404, "Apontamento não encontrado.")
    db.delete(ap)
    db.commit()


@router.post("/atividades/{atividade_id}/reabrir", response_model=AtividadeOut)
def reabrir(atividade_id: int, db: Session = Depends(get_db)):
    a = _obter(db, atividade_id)
    a.fim_real = None
    db.commit()
    db.refresh(a)
    return atividade_dict(a)


# ---------- Indicadores ----------

@router.get("/indicadores", tags=["indicadores"])
def obter_indicadores(
    inicio: date | None = None,
    fim: date | None = None,
    frente: str | None = None,
    tipo: str | None = None,
    data_ref: date | None = None,
    db: Session = Depends(get_db),
):
    return indicadores(listar_atividades(db, inicio, fim, frente, tipo), data_ref)
