"""Feeds tabulares (JSON plano ou CSV) para consumo pelo Power BI.

No Power BI Desktop: Obter Dados > Web > http://<servidor>:8000/api/powerbi/atividades
Se MINEPLAN_POWERBI_TOKEN estiver definido, envie o cabeçalho "X-API-Key" com o token
(Web > Avançado > Parâmetros de cabeçalho HTTP) ou use ?token=... na URL.
"""
import csv
import io
import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import listar_atividades
from ..status import calcular_situacao, indicadores, semana_iso

router = APIRouter(prefix="/api/powerbi", tags=["power bi"])


def verificar_token(x_api_key: str | None = Header(None), token: str | None = Query(None)):
    esperado = os.getenv("MINEPLAN_POWERBI_TOKEN")
    if esperado and (x_api_key or token) != esperado:
        raise HTTPException(401, "Token do Power BI inválido ou ausente.")


def _saida(linhas: list[dict], formato: str, nome: str):
    if formato == "csv":
        buf = io.StringIO()
        if linhas:
            w = csv.DictWriter(buf, fieldnames=list(linhas[0]), delimiter=";")
            w.writeheader()
            w.writerows(linhas)
        return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{nome}.csv"'})
    return linhas


Formato = Query("json", pattern="^(json|csv)$")


@router.get("/atividades", dependencies=[Depends(verificar_token)])
def feed_atividades(inicio: date | None = None, fim: date | None = None, data_ref: date | None = None,
                    formato: str = Formato, db: Session = Depends(get_db)):
    linhas = []
    for a in listar_atividades(db, inicio, fim):
        s = calcular_situacao(a, data_ref)
        linhas.append({
            "id": a.id, "codigo": a.codigo, "descricao": a.descricao, "tipo": a.tipo, "frente": a.frente,
            "equipamento": a.equipamento, "responsavel": a.responsavel, "unidade": a.unidade,
            "qtd_planejada": a.qtd_planejada, "qtd_realizada": s.qtd_realizada, "qtd_esperada": s.qtd_esperada,
            "saldo": s.saldo, "projecao": s.projecao, "impacto_meta": s.impacto_meta,
            "inicio_planejado": a.inicio_planejado.isoformat(), "fim_planejado": a.fim_planejado.isoformat(),
            "inicio_real": a.inicio_real.isoformat() if a.inicio_real else None,
            "fim_real": a.fim_real.isoformat() if a.fim_real else None,
            "semana": semana_iso(a.inicio_planejado),
            "progresso_real": s.progresso_real, "progresso_esperado": s.progresso_esperado, "desvio": s.desvio,
            "status": s.status, "situacao": s.rotulo, "dias_atraso": s.dias_atraso,
            "concluida_com_atraso": s.concluida_com_atraso,
        })
    return _saida(linhas, formato, "atividades")


@router.get("/apontamentos", dependencies=[Depends(verificar_token)])
def feed_apontamentos(inicio: date | None = None, fim: date | None = None,
                      formato: str = Formato, db: Session = Depends(get_db)):
    linhas = [
        {"id": p.id, "atividade_id": a.id, "codigo": a.codigo, "tipo": a.tipo, "frente": a.frente,
         "unidade": a.unidade, "data": p.data.isoformat(), "semana": semana_iso(p.data),
         "quantidade": p.quantidade, "observacao": p.observacao}
        for a in listar_atividades(db, inicio, fim) for p in a.apontamentos
    ]
    return _saida(linhas, formato, "apontamentos")


@router.get("/plano-diario", dependencies=[Depends(verificar_token)])
def feed_plano_diario(inicio: date | None = None, fim: date | None = None,
                      formato: str = Formato, db: Session = Depends(get_db)):
    """Quantidade planejada distribuída linearmente por dia (para curvas planejado x realizado)."""
    linhas = []
    for a in listar_atividades(db, inicio, fim, incluir_pendentes=False):
        dias =(a.fim_planejado - a.inicio_planejado).days + 1
        por_dia = (a.qtd_planejada or 0) / dias
        for i in range(dias):
            d = a.inicio_planejado + timedelta(days=i)
            if (inicio and d < inicio) or (fim and d > fim):
                continue
            linhas.append({"atividade_id": a.id, "codigo": a.codigo, "tipo": a.tipo, "frente": a.frente,
                           "unidade": a.unidade, "data": d.isoformat(), "semana": semana_iso(d),
                           "qtd_planejada_dia": round(por_dia, 4)})
    return _saida(linhas, formato, "plano_diario")


@router.get("/indicadores", dependencies=[Depends(verificar_token)])
def feed_indicadores(inicio: date | None = None, fim: date | None = None, data_ref: date | None = None,
                     formato: str = Formato, db: Session = Depends(get_db)):
    ind = indicadores(listar_atividades(db, inicio, fim), data_ref)
    linhas = [p | {"data_referencia": ind["data_referencia"].isoformat()} for p in ind["producao"]]
    return _saida(linhas, formato, "indicadores")
