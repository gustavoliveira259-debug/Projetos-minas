"""Importação de planilhas e exportação para Excel."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..exporter import exportar_excel, modelo_importacao
from ..importer import ler_planilha
from ..models import Apontamento, Atividade
from ..services import listar_atividades

router = APIRouter(prefix="/api", tags=["importação e exportação"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TAMANHO_MAX = 15 * 1024 * 1024


def _xlsx(conteudo: bytes, nome: str) -> Response:
    return Response(conteudo, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/importacao/modelo")
def baixar_modelo():
    return _xlsx(modelo_importacao(), "modelo_planejamento_mineplan.xlsx")


@router.post("/importacao")
async def importar(
    arquivo: UploadFile = File(...),
    confirmar: bool = Query(False, description="false = só pré-visualiza; true = grava no banco"),
    modo: Literal["mesclar", "substituir"] = Query(
        "mesclar", description="mesclar: atualiza pelo código e adiciona novas; substituir: apaga tudo antes"),
    db: Session = Depends(get_db),
):
    nome = arquivo.filename or ""
    if not nome.lower().endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(415, "Envie um arquivo .xlsx, .xlsm ou .csv.")
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX:
        raise HTTPException(413, "Arquivo maior que 15 MB.")
    try:
        leitura = ler_planilha(conteudo, nome)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        raise HTTPException(422, "Não foi possível ler o arquivo. Verifique se é uma planilha válida.")

    existentes = {} if modo == "substituir" else {
        a.codigo: a for a in db.scalars(select(Atividade).where(Atividade.codigo.is_not(None)))
    }

    previa = []
    for l in leitura.linhas:
        cod = l.dados.get("codigo")
        acao = "erro" if l.erros else ("atualizar" if cod and cod in existentes else "criar")
        previa.append({"linha": l.linha, "acao": acao, "erros": l.erros, "dados": l.dados,
                       "qtd_realizada": l.qtd_realizada})

    resumo = {
        "arquivo": nome,
        "aba": leitura.aba,
        "linha_cabecalho": leitura.linha_cabecalho,
        "colunas_reconhecidas": leitura.colunas_reconhecidas,
        "colunas_ignoradas": leitura.colunas_ignoradas,
        "total_linhas": len(leitura.linhas),
        "criar": sum(p["acao"] == "criar" for p in previa),
        "atualizar": sum(p["acao"] == "atualizar" for p in previa),
        "com_erro": sum(p["acao"] == "erro" for p in previa),
        "modo": modo,
        "confirmado": False,
    }

    if not confirmar:
        return resumo | {"linhas": previa}

    if modo == "substituir":
        db.execute(delete(Apontamento))
        db.execute(delete(Atividade))

    hoje = date.today()
    vistos: dict[str, Atividade] = {}
    for l in leitura.validas:
        d = l.dados
        cod = d.get("codigo")
        a = (vistos.get(cod) or existentes.get(cod)) if cod else None
        if a is None:
            a = Atividade(**({"unidade": "t", "qtd_planejada": 0.0} | {k: v for k, v in d.items() if v is not None}))
            db.add(a)
        else:
            for k, v in d.items():
                if v is not None:
                    setattr(a, k, v)
        if cod:
            vistos[cod] = a

        # Quantidade realizada da planilha vira um apontamento de ajuste (mantém o histórico).
        if l.qtd_realizada is not None:
            delta = round(l.qtd_realizada - a.qtd_realizada, 4)
            if delta:
                data_ap = d.get("fim_real") or min(hoje, d["fim_planejado"])
                data_ap = max(data_ap, d.get("inicio_real") or d["inicio_planejado"])
                a.apontamentos.append(Apontamento(data=data_ap, quantidade=delta,
                                                  observacao=f"Importado de {nome}"))
                if a.inicio_real is None and l.qtd_realizada > 0:
                    a.inicio_real = d.get("inicio_real") or d["inicio_planejado"]
    db.commit()
    return resumo | {"confirmado": True, "linhas": [p for p in previa if p["acao"] == "erro"]}


@router.get("/exportacao/excel")
def exportar(
    inicio: date | None = None,
    fim: date | None = None,
    frente: str | None = None,
    tipo: str | None = None,
    data_ref: date | None = None,
    db: Session = Depends(get_db),
):
    ats = listar_atividades(db, inicio, fim, frente, tipo)
    sufixo = f"{inicio:%Y%m%d}_{fim:%Y%m%d}" if inicio and fim else f"{date.today():%Y%m%d}"
    return _xlsx(exportar_excel(ats, data_ref), f"mineplan_{sufixo}.xlsx")
