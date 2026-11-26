import io
from datetime import date, datetime

import pytest
from openpyxl import load_workbook

from app import frota

from app.frota import codigos_da_atividade

SEMANA = {"inicio": "2025-11-24", "fim": "2025-11-30"}
CG = {"codigo": "CG-1", "descricao": "Carregamento estéril", "tipo": "Carregamento", "frente": "Cava Sul",
      "equipamento": "ES-02", "unidade": "t", "qtd_planejada": 70000,
      "inicio_planejado": "2025-11-24", "fim_planejado": "2025-11-30"}


@pytest.fixture(autouse=True)
def relogio(monkeypatch):
    """Testes rodam "dentro" da semana de 24 a 30/11/2025, na quinta às 18h."""
    monkeypatch.setattr(frota, "relogio", lambda: datetime(2025, 11, 27, 18, 0))


def _equip(client, codigo, **kw):
    r = client.post("/api/equipamentos", json={"codigo": codigo, "categoria": "Escavadeira", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _painel(client, ref="2025-11-27", **kw):
    r = client.get("/api/equipamentos/painel", params={**SEMANA, "data_ref": ref, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_codigos_da_atividade():
    assert codigos_da_atividade("CM-07/08/09") == ["CM-07", "CM-08", "CM-09"]
    assert codigos_da_atividade("ES-01 + CM-10, CM-11") == ["ES-01", "CM-10", "CM-11"]
    assert codigos_da_atividade("es-01") == ["ES-01"]
    assert codigos_da_atividade(None) == []


def test_crud_e_codigo_duplicado(client):
    e = _equip(client, "es-02", descricao="PC700")
    assert e["codigo"] == "ES-02"
    assert client.post("/api/equipamentos", json={"codigo": "ES-02"}).status_code == 409
    r = client.patch(f"/api/equipamentos/{e['id']}", json={"frente": "Cava Sul", "meta_df": 0.9})
    assert r.json()["frente"] == "Cava Sul" and r.json()["meta_df"] == 0.9
    assert client.delete(f"/api/equipamentos/{e['id']}").status_code == 204
    assert client.get("/api/equipamentos").json() == []


def test_disponibilidade_utilizacao_e_mttr(client):
    e = _equip(client, "ES-02")
    url = f"/api/equipamentos/{e['id']}"
    # Corretiva de 12 h na segunda, preventiva de 6 h na terça, operacional de 4 h (não conta na DF)
    for p in [
        {"tipo": "corretiva", "inicio": "2025-11-24T08:00", "fim": "2025-11-24T20:00"},
        {"tipo": "preventiva", "inicio": "2025-11-25T06:00", "fim": "2025-11-25T12:00"},
        {"tipo": "operacional", "inicio": "2025-11-26T00:00", "fim": "2025-11-26T04:00"},
    ]:
        assert client.post(f"{url}/paradas", json=p).status_code == 201
    # Sobreposição com outra parada é recusada
    r = client.post(f"{url}/paradas", json={"tipo": "corretiva", "inicio": "2025-11-24T10:00",
                                            "fim": "2025-11-24T11:00"})
    assert r.status_code == 409
    for dia in ("2025-11-24", "2025-11-25", "2025-11-26"):
        client.post(f"{url}/horas", json={"data": dia, "horas_trabalhadas": 15})

    eq = _painel(client, ref="2025-11-26")["equipamentos"][0]   # até o fim de quarta = 72 h
    assert eq["horas_calendario"] == 72
    assert eq["horas_corretiva"] == 12 and eq["horas_preventiva"] == 6 and eq["horas_operacional"] == 4
    assert eq["df"] == round((72 - 18) / 72, 4)
    assert eq["uf"] == round(45 / 54, 4)
    assert eq["corretivas"] == 1 and eq["mttr_h"] == 12
    assert eq["df_prevista"] == round((168 - 18) / 168, 4)


def test_parada_em_aberto_e_conflito_com_atividade(client):
    e = _equip(client, "ES-02")
    a = client.post("/api/atividades", json=CG).json()
    # Quebrou na terça às 12h e continua parada
    client.post(f"/api/equipamentos/{e['id']}/paradas",
                json={"tipo": "corretiva", "inicio": "2025-11-25T12:00", "motivo": "Vazamento hidráulico"})
    # Preventiva programada para sábado (futura em relação à referência)
    client.post(f"/api/equipamentos/{e['id']}/paradas",
                json={"tipo": "preventiva", "inicio": "2025-11-29T07:00", "fim": "2025-11-29T19:00"})

    p = _painel(client, ref="2025-11-27")
    eq = p["equipamentos"][0]
    assert eq["status"] == "manutencao" and eq["parada_atual"]["motivo"] == "Vazamento hidráulico"
    # Em aberto conta até agora: terça 12h -> quinta 18h = 54 h
    assert eq["horas_corretiva"] == 54
    assert eq["horas_manutencao_programada"] == 12

    conf = p["conflitos"]
    assert {c["tipo_parada"] for c in conf} == {"corretiva", "preventiva"}
    assert all(c["atividade_id"] == a["id"] for c in conf)
    prev = next(c for c in conf if c["tipo_parada"] == "preventiva")
    assert prev["programada"] and prev["horas_sobrepostas"] == 12
    assert prev["perda_capacidade"] == round(12 / 168, 4)
    assert prev["producao_em_risco"] == round(70000 * 12 / 168, 2)
    assert p["resumo"]["atividades_afetadas"] == 1

    # Encerrar a parada: equipamento volta a operar (tem atividade em andamento)
    pid = eq["parada_atual"]["id"]
    assert client.patch(f"/api/paradas/{pid}", json={"fim": "2025-11-26T18:00"}).status_code == 200
    eq = _painel(client, ref="2025-11-27")["equipamentos"][0]
    assert eq["status"] == "operando" and eq["horas_corretiva"] == 30


def test_capacidade_dividida_entre_equipamentos(client):
    e = _equip(client, "CM-08", categoria="Caminhão")
    client.post("/api/atividades", json=CG | {"equipamento": "CM-07/08/09", "qtd_planejada": 52000})
    client.post(f"/api/equipamentos/{e['id']}/paradas",
                json={"tipo": "corretiva", "inicio": "2025-11-24T00:00", "fim": "2025-11-25T00:00"})
    p = _painel(client)
    c = p["conflitos"][0]
    assert c["equipamentos_na_atividade"] == 3
    assert c["perda_capacidade"] == round(24 / (168 * 3), 4)
    assert p["nao_cadastrados"] == ["CM-07", "CM-09"]


def test_preventiva_por_horimetro(client):
    e = _equip(client, "PF-03", intervalo_preventiva_h=250, horimetro_ultima_preventiva=3000)
    url = f"/api/equipamentos/{e['id']}"
    client.post(f"{url}/horas", json={"data": "2025-11-24", "horas_trabalhadas": 18, "horimetro": 3230})
    assert _painel(client)["equipamentos"][0]["preventiva"]["estado"] == "proxima"
    client.post(f"{url}/horas", json={"data": "2025-11-25", "horas_trabalhadas": 20, "horimetro": 3255})
    prev = _painel(client)["equipamentos"][0]["preventiva"]
    assert prev["estado"] == "vencida" and prev["restante_h"] == -5
    # Registrar a preventiva realizada com o horímetro zera o contador
    client.post(f"{url}/paradas", json={"tipo": "preventiva", "inicio": "2025-11-26T07:00",
                                        "fim": "2025-11-26T15:00", "horimetro": 3256})
    prev = _painel(client)["equipamentos"][0]["preventiva"]
    assert prev["estado"] == "ok" and prev["restante_h"] == 250


def test_sincronizar_a_partir_das_atividades(client):
    client.post("/api/atividades", json=CG | {"equipamento": "CM-10/11"})
    client.post("/api/atividades", json=CG | {"codigo": "PF", "equipamento": "PF-05"})
    _equip(client, "CM-10")
    r = client.post("/api/equipamentos/sincronizar")
    assert r.json()["criados"] == ["CM-11", "PF-05"]
    cats = {e["codigo"]: e["categoria"] for e in client.get("/api/equipamentos").json()}
    assert cats["CM-11"] == "Caminhão" and cats["PF-05"] == "Perfuratriz"


def test_exportacao_com_frota(client):
    e = _equip(client, "ES-02")
    client.post("/api/atividades", json=CG)
    client.post(f"/api/equipamentos/{e['id']}/paradas",
                json={"tipo": "corretiva", "inicio": "2025-11-25T08:00", "fim": "2025-11-25T10:00"})
    r = client.get("/api/exportacao/excel", params={**SEMANA, "data_ref": "2025-11-27"})
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[-3:] == ["Equipamentos", "Paradas", "Conflitos"]
    assert wb["Equipamentos"]["A2"].value == "ES-02"
    assert wb["Paradas"]["D2"].value == datetime(2025, 11, 25, 8, 0)
    assert wb["Conflitos"]["F2"].value == "ES-02"


def test_seed_frota():
    from app import seed
    seed.popular(limpar=True, hoje=date(2026, 11, 26))
