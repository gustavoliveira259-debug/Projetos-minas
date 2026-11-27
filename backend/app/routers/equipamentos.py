from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import frota
from ..frota import analisar_frota, codigos_da_atividade, normalizar
from ..models import Atividade, Equipamento, Parada, RegistroHoras
from ..schemas import (
    EquipamentoCreate, EquipamentoOut, EquipamentoUpdate, ParadaCreate, ParadaOut, ParadaUpdate,
    RegistroHorasCreate, RegistroHorasOut,
)
from ..services import listar_atividades
from ..status import inicio_semana

router = APIRouter(prefix="/api", tags=["equipamentos"])

# Prefixo usual do código -> categoria (usado ao cadastrar a partir das atividades)
CATEGORIA_POR_PREFIXO = {
    "PF": "Perfuratriz", "ES": "Escavadeira", "CM": "Caminhão", "PC": "Pá carregadeira",
    "MN": "Motoniveladora", "TE": "Trator de esteira", "CP": "Caminhão-pipa", "RE": "Retroescavadeira",
}


def listar_equipamentos(db: Session) -> list[Equipamento]:
    stmt = (select(Equipamento)
            .options(selectinload(Equipamento.paradas), selectinload(Equipamento.registros_horas))
            .order_by(Equipamento.categoria, Equipamento.codigo))
    return list(db.scalars(stmt))


def periodo_frota(inicio: date | None, fim: date | None, ref: date | None) -> tuple[date, date, date]:
    """Sem período informado ("todas as datas"), analisa a semana da data de referência."""
    ref = ref or date.today()
    if not inicio or not fim:
        inicio = inicio_semana(ref)
        fim = inicio + timedelta(days=6)
    return inicio, fim, ref


def _obter(db: Session, equipamento_id: int) -> Equipamento:
    e = db.get(Equipamento, equipamento_id)
    if not e:
        raise HTTPException(404, "Equipamento não encontrado.")
    return e


def _salvar(db: Session):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe um equipamento com este código.")


@router.get("/equipamentos", response_model=list[EquipamentoOut])
def listar(db: Session = Depends(get_db)):
    return listar_equipamentos(db)


@router.get("/equipamentos/painel")
def painel(inicio: date | None = None, fim: date | None = None, data_ref: date | None = None,
           db: Session = Depends(get_db)):
    """Disponibilidade, utilização, manutenção e conflitos com o planejamento no período."""
    inicio, fim, ref = periodo_frota(inicio, fim, data_ref)
    return analisar_frota(listar_equipamentos(db), listar_atividades(db, inicio, fim), inicio, fim, ref)


@router.post("/equipamentos/sincronizar")
def sincronizar(db: Session = Depends(get_db)):
    """Cadastra os equipamentos citados nas atividades que ainda não existem."""
    existentes = {normalizar(c) for c in db.scalars(select(Equipamento.codigo))}
    frentes: dict[str, str | None] = {}
    for a in db.scalars(select(Atividade).order_by(Atividade.inicio_planejado.desc())):
        for c in codigos_da_atividade(a.equipamento):
            frentes.setdefault(c, a.frente)
    novos = []
    for c, frente in sorted(frentes.items()):
        if c in existentes:
            continue
        prefixo = c.split("-")[0]
        db.add(Equipamento(codigo=c, categoria=CATEGORIA_POR_PREFIXO.get(prefixo), frente=frente))
        novos.append(c)
    db.commit()
    return {"criados": novos}


@router.post("/equipamentos", response_model=EquipamentoOut, status_code=201)
def criar(dados: EquipamentoCreate, db: Session = Depends(get_db)):
    e = Equipamento(**dados.model_dump() | {"codigo": dados.codigo.strip().upper()})
    db.add(e)
    _salvar(db)
    db.refresh(e)
    return e


@router.get("/equipamentos/{equipamento_id}", response_model=EquipamentoOut)
def obter(equipamento_id: int, db: Session = Depends(get_db)):
    return _obter(db, equipamento_id)


@router.patch("/equipamentos/{equipamento_id}", response_model=EquipamentoOut)
def atualizar(equipamento_id: int, dados: EquipamentoUpdate, db: Session = Depends(get_db)):
    e = _obter(db, equipamento_id)
    mudancas = dados.model_dump(exclude_unset=True)
    if "codigo" in mudancas:
        if not mudancas["codigo"]:
            raise HTTPException(422, "O código é obrigatório.")
        mudancas["codigo"] = mudancas["codigo"].strip().upper()
    for k, v in mudancas.items():
        setattr(e, k, v)
    _salvar(db)
    db.refresh(e)
    return e


@router.delete("/equipamentos/{equipamento_id}", status_code=204)
def excluir(equipamento_id: int, db: Session = Depends(get_db)):
    db.delete(_obter(db, equipamento_id))
    db.commit()


# ---------- Paradas (manutenção e paradas operacionais) ----------

def _validar_parada(e: Equipamento, inicio: datetime, fim: datetime | None, ignorar: int | None = None):
    if fim and fim <= inicio:
        raise HTTPException(422, "O fim da parada deve ser posterior ao início.")
    # Uma parada em aberto ocupa o intervalo até agora: dá para programar uma preventiva futura
    # enquanto o equipamento ainda está em corretiva, mas não duas paradas em aberto ao mesmo tempo.
    agora = frota.relogio()
    if fim is None and any(p.fim is None and p.id != ignorar for p in e.paradas):
        raise HTTPException(409, f"{e.codigo} já tem uma parada em aberto. Encerre-a antes de abrir outra.")
    for p in e.paradas:
        if p.id == ignorar:
            continue
        p_fim = p.fim or max(agora, p.inicio + timedelta(seconds=1))
        n_fim = fim or max(agora, inicio + timedelta(seconds=1))
        if inicio < p_fim and p.inicio < n_fim:
            raise HTTPException(409, f"Já existe uma parada de {e.codigo} nesse intervalo "
                                     f"(início {p.inicio:%d/%m %H:%M}).")


def _atualizar_preventiva(e: Equipamento, p: Parada):
    if p.tipo == "preventiva" and p.horimetro is not None and p.inicio <= frota.relogio():
        if e.horimetro_ultima_preventiva is None or p.horimetro >= e.horimetro_ultima_preventiva:
            e.horimetro_ultima_preventiva = p.horimetro


@router.get("/equipamentos/{equipamento_id}/paradas", response_model=list[ParadaOut])
def listar_paradas(equipamento_id: int, db: Session = Depends(get_db)):
    return _obter(db, equipamento_id).paradas


@router.post("/equipamentos/{equipamento_id}/paradas", response_model=ParadaOut, status_code=201)
def criar_parada(equipamento_id: int, dados: ParadaCreate, db: Session = Depends(get_db)):
    e = _obter(db, equipamento_id)
    _validar_parada(e, dados.inicio, dados.fim)
    p = Parada(**dados.model_dump())
    e.paradas.append(p)
    _atualizar_preventiva(e, p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/paradas/{parada_id}", response_model=ParadaOut)
def atualizar_parada(parada_id: int, dados: ParadaUpdate, db: Session = Depends(get_db)):
    p = db.get(Parada, parada_id)
    if not p:
        raise HTTPException(404, "Parada não encontrada.")
    mudancas = dados.model_dump(exclude_unset=True)
    _validar_parada(p.equipamento, mudancas.get("inicio", p.inicio), mudancas.get("fim", p.fim), ignorar=p.id)
    for k, v in mudancas.items():
        setattr(p, k, v)
    _atualizar_preventiva(p.equipamento, p)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/paradas/{parada_id}", status_code=204)
def excluir_parada(parada_id: int, db: Session = Depends(get_db)):
    p = db.get(Parada, parada_id)
    if not p:
        raise HTTPException(404, "Parada não encontrada.")
    db.delete(p)
    db.commit()


# ---------- Horas trabalhadas / horímetro ----------

@router.get("/equipamentos/{equipamento_id}/horas", response_model=list[RegistroHorasOut])
def listar_horas(equipamento_id: int, db: Session = Depends(get_db)):
    return _obter(db, equipamento_id).registros_horas


@router.post("/equipamentos/{equipamento_id}/horas", response_model=RegistroHorasOut, status_code=201)
def registrar_horas(equipamento_id: int, dados: RegistroHorasCreate, db: Session = Depends(get_db)):
    e = _obter(db, equipamento_id)
    r = RegistroHoras(**dados.model_dump())
    e.registros_horas.append(r)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/horas/{registro_id}", status_code=204)
def excluir_horas(registro_id: int, db: Session = Depends(get_db)):
    r = db.get(RegistroHoras, registro_id)
    if not r:
        raise HTTPException(404, "Registro não encontrado.")
    db.delete(r)
    db.commit()
