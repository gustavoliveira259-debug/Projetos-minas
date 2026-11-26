import io
from datetime import date

from openpyxl import Workbook, load_workbook

from app.importer import para_data, para_numero

NOVA = {
    "codigo": "CG-1", "descricao": "Carregamento minério", "tipo": "Carregamento", "frente": "Cava Norte",
    "unidade": "t", "qtd_planejada": 1000, "inicio_planejado": "2026-11-23", "fim_planejado": "2026-11-27",
}


def test_crud_e_apontamento(client):
    r = client.post("/api/atividades", json=NOVA)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]

    r = client.patch(f"/api/atividades/{aid}", json={"fim_planejado": "2026-11-20"})
    assert r.status_code == 422  # fim antes do início

    r = client.patch(f"/api/atividades/{aid}", json={"fim_planejado": "2026-11-28", "equipamento": "ES-01"})
    assert r.json()["fim_planejado"] == "2026-11-28" and r.json()["equipamento"] == "ES-01"

    r = client.post(f"/api/atividades/{aid}/apontamentos", json={"data": "2026-11-23", "quantidade": 400})
    assert r.status_code == 201
    body = r.json()
    assert body["qtd_realizada"] == 400 and body["inicio_real"] == "2026-11-23"

    r = client.get("/api/atividades", params={"data_ref": "2026-11-24"})
    assert r.json()[0]["situacao"]["status"] == "adiantada"

    r = client.post(f"/api/atividades/{aid}/apontamentos",
                    json={"data": "2026-11-25", "quantidade": 0, "concluir": True})
    assert r.json()["situacao"]["status"] == "concluida"

    aps = client.get(f"/api/atividades/{aid}/apontamentos").json()
    assert len(aps) == 1
    assert client.delete(f"/api/apontamentos/{aps[0]['id']}").status_code == 204
    assert client.delete(f"/api/atividades/{aid}").status_code == 204
    assert client.get(f"/api/atividades/{aid}").status_code == 404


def test_filtro_por_semana(client):
    client.post("/api/atividades", json=NOVA)
    client.post("/api/atividades", json=NOVA | {"codigo": "X", "inicio_planejado": "2026-12-07",
                                                 "fim_planejado": "2026-12-08"})
    # Da semana anterior: uma ainda aberta (deve aparecer) e uma concluída antes (não deve)
    client.post("/api/atividades", json=NOVA | {"codigo": "ABERTA", "inicio_planejado": "2026-11-16",
                                                 "fim_planejado": "2026-11-18"})
    fechada = client.post("/api/atividades", json=NOVA | {"codigo": "FECHADA", "inicio_planejado": "2026-11-16",
                                                           "fim_planejado": "2026-11-18"}).json()
    client.post(f"/api/atividades/{fechada['id']}/apontamentos",
                json={"data": "2026-11-18", "quantidade": 1000})
    r = client.get("/api/atividades", params={"inicio": "2026-11-23", "fim": "2026-11-29", "data_ref": "2026-11-24"})
    codigos = {a["codigo"]: a for a in r.json()}
    assert set(codigos) == {"CG-1", "ABERTA"}
    assert codigos["ABERTA"]["situacao"]["status"] == "atrasada"
    assert codigos["ABERTA"]["situacao"]["dias_atraso"] == 6


def _planilha(linhas):
    wb = Workbook()
    ws = wb.active
    ws.append(["Relatório semanal BEMISA"])  # título acima do cabeçalho
    ws.append(["Cód.", "Descrição da Atividade", "Frente de Lavra", "Unid.", "Volume", "Realizado",
               "Início", "Término", "Coluna extra"])
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_importacao_previa_e_confirmacao(client):
    arq = _planilha([
        ["A1", "Perfuração", "Cava Sul", "m", 1200, 300, date(2026, 11, 23), date(2026, 11, 25), "x"],
        ["A2", "Desmonte", "Cava Sul", "t", "45.000", None, "26/11/2026", "26/11/2026", None],
        ["A3", None, "Cava Sul", "t", 10, None, "26/11/2026", "25/11/2026", None],
    ])
    files = {"arquivo": ("plano.xlsx", arq)}
    r = client.post("/api/importacao", files=files)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["criar"] == 2 and p["com_erro"] == 1 and not p["confirmado"]
    assert p["colunas_ignoradas"] == ["Coluna extra"]
    assert client.get("/api/atividades").json() == []

    r = client.post("/api/importacao", params={"confirmar": True}, files=files)
    assert r.json()["confirmado"]
    ats = {a["codigo"]: a for a in client.get("/api/atividades").json()}
    assert ats["A1"]["qtd_realizada"] == 300 and ats["A1"]["unidade"] == "m"
    assert ats["A2"]["qtd_planejada"] == 45000

    # Reimportar no modo mesclar atualiza pelo código e ajusta o realizado
    arq2 = _planilha([["A1", "Perfuração", "Cava Sul", "m", 1300, 500, date(2026, 11, 23), date(2026, 11, 25), ""]])
    r = client.post("/api/importacao", params={"confirmar": True}, files={"arquivo": ("plano.xlsx", arq2)})
    assert r.json()["atualizar"] == 1
    ats = {a["codigo"]: a for a in client.get("/api/atividades").json()}
    assert len(ats) == 2 and ats["A1"]["qtd_planejada"] == 1300 and ats["A1"]["qtd_realizada"] == 500


def test_importacao_csv_ponto_e_virgula(client):
    csv = "Atividade;Início;Fim;Quantidade\nTransporte;23/11/2026;27/11/2026;1.234,5\n".encode("cp1252")
    r = client.post("/api/importacao", params={"confirmar": True}, files={"arquivo": ("p.csv", csv)})
    assert r.status_code == 200, r.text
    assert client.get("/api/atividades").json()[0]["qtd_planejada"] == 1234.5


def test_importacao_sem_colunas_obrigatorias(client):
    wb = Workbook()
    wb.active.append(["Foo", "Bar"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/importacao", files={"arquivo": ("x.xlsx", buf.getvalue())})
    assert r.status_code == 422


def test_exportacao_e_modelo(client):
    client.post("/api/atividades", json=NOVA)
    r = client.get("/api/exportacao/excel")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Resumo", "Por frente", "Atividades", "Apontamentos", "Indicadores"]  # sem frota
    assert wb["Atividades"]["C2"].value == "Carregamento minério"

    r = client.get("/api/importacao/modelo")
    modelo = client.post("/api/importacao", files={"arquivo": ("m.xlsx", r.content)}).json()
    assert modelo["criar"] == 3 and modelo["com_erro"] == 0


def test_powerbi_json_csv_e_token(client, monkeypatch):
    client.post("/api/atividades", json=NOVA)
    r = client.get("/api/powerbi/atividades")
    assert r.json()[0]["semana"] == "2026-S48"
    assert len(client.get("/api/powerbi/plano-diario").json()) == 5
    assert client.get("/api/powerbi/atividades", params={"formato": "csv"}).text.startswith("﻿id;codigo")

    monkeypatch.setenv("MINEPLAN_POWERBI_TOKEN", "segredo")
    assert client.get("/api/powerbi/atividades").status_code == 401
    assert client.get("/api/powerbi/atividades", headers={"X-API-Key": "segredo"}).status_code == 200


def test_conversoes():
    assert para_numero("1.234,56") == 1234.56
    assert para_numero("1.234.567") == 1234567
    assert para_numero("12.5") == 12.5
    assert para_data(46349) == date(2026, 11, 23)
    assert para_data("23/11/26") == date(2026, 11, 23)
