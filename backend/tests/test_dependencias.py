BASE = {"tipo": "Perfuração", "frente": "Cava Norte", "unidade": "m", "qtd_planejada": 100}


def criar(client, codigo, ini, fim, **extra):
    r = client.post("/api/atividades", json=BASE | {"codigo": codigo, "descricao": codigo,
                                                    "inicio_planejado": ini, "fim_planejado": fim} | extra)
    assert r.status_code == 201, r.text
    return r.json()


def test_responsavel_salvo_e_listado(client):
    a = criar(client, "PF-1", "2026-12-01", "2026-12-02", responsavel="Ana Souza")
    assert a["responsavel"] == "Ana Souza"
    r = client.patch(f"/api/atividades/{a['id']}", json={"responsavel": "Bruno Lima"})
    assert r.json()["responsavel"] == "Bruno Lima"
    assert client.get("/api/atividades/filtros").json()["responsaveis"] == ["Bruno Lima"]


def test_mover_principal_empurra_dependentes_em_cascata(client):
    pf = criar(client, "PF", "2026-12-01", "2026-12-02")
    dm = criar(client, "DM", "2026-12-03", "2026-12-03", predecessoras=[pf["id"]])
    cg = criar(client, "CG", "2026-12-03", "2026-12-06", predecessoras=[dm["id"]])
    assert [p["codigo"] for p in dm["predecessoras"]] == ["PF"]

    # Perfuração atrasa 3 dias: termina em 05/12 -> desmonte vai p/ 05/12, carregamento p/ 05/12–08/12
    r = client.patch(f"/api/atividades/{pf['id']}", json={"inicio_planejado": "2026-12-04", "fim_planejado": "2026-12-05"})
    assert r.status_code == 200, r.text
    assert {x["codigo"] for x in r.json()["empurradas"]} == {"DM", "CG"}
    dm2 = client.get(f"/api/atividades/{dm['id']}").json()
    cg2 = client.get(f"/api/atividades/{cg['id']}").json()
    assert (dm2["inicio_planejado"], dm2["fim_planejado"]) == ("2026-12-05", "2026-12-05")
    assert (cg2["inicio_planejado"], cg2["fim_planejado"]) == ("2026-12-05", "2026-12-08")  # duração mantida
    assert [s["codigo"] for s in client.get(f"/api/atividades/{pf['id']}").json()["sucessoras"]] == ["DM"]


def test_folga_absorve_e_adiantar_nao_puxa(client):
    pf = criar(client, "PF", "2026-12-01", "2026-12-02")
    dm = criar(client, "DM", "2026-12-05", "2026-12-05", predecessoras=[pf["id"]])
    # Estender até 04/12 cabe na folga: dependente não se mexe
    r = client.patch(f"/api/atividades/{pf['id']}", json={"fim_planejado": "2026-12-04"})
    assert r.json()["empurradas"] == []
    # Adiantar a principal não puxa a dependente
    client.patch(f"/api/atividades/{pf['id']}", json={"inicio_planejado": "2026-11-28", "fim_planejado": "2026-11-29"})
    assert client.get(f"/api/atividades/{dm['id']}").json()["inicio_planejado"] == "2026-12-05"


def test_dependente_nao_comeca_antes_da_principal(client):
    pf = criar(client, "PF", "2026-12-01", "2026-12-03")
    r = client.post("/api/atividades", json=BASE | {"codigo": "DM", "descricao": "DM", "inicio_planejado": "2026-12-02",
                                                    "fim_planejado": "2026-12-02", "predecessoras": [pf["id"]]})
    assert r.status_code == 422 and "03/12/2026" in r.json()["detail"]
    dm = criar(client, "DM", "2026-12-03", "2026-12-03", predecessoras=[pf["id"]])  # mesmo dia do fim: permitido
    r = client.patch(f"/api/atividades/{dm['id']}", json={"inicio_planejado": "2026-12-01", "fim_planejado": "2026-12-01"})
    assert r.status_code == 422


def test_ciclo_e_autodependencia_rejeitados(client):
    a = criar(client, "A", "2026-12-01", "2026-12-01")
    b = criar(client, "B", "2026-12-02", "2026-12-02", predecessoras=[a["id"]])
    assert client.patch(f"/api/atividades/{a['id']}", json={"predecessoras": [a["id"]]}).status_code == 422
    r = client.patch(f"/api/atividades/{a['id']}", json={"predecessoras": [b["id"]]})
    assert r.status_code == 422 and "ciclo" in r.json()["detail"]
    assert client.patch(f"/api/atividades/{b['id']}", json={"predecessoras": [999]}).status_code == 422


def test_remover_dependencia_e_excluir_principal(client):
    a = criar(client, "A", "2026-12-01", "2026-12-01")
    b = criar(client, "B", "2026-12-02", "2026-12-02", predecessoras=[a["id"]])
    assert client.patch(f"/api/atividades/{b['id']}", json={"predecessoras": []}).json()["predecessoras"] == []
    client.patch(f"/api/atividades/{b['id']}", json={"predecessoras": [a["id"]]})
    assert client.delete(f"/api/atividades/{a['id']}").status_code == 204
    assert client.get(f"/api/atividades/{b['id']}").json()["predecessoras"] == []
