from datetime import date

from app.models import Apontamento, Atividade
from app.status import aderencia, calcular_situacao, indicadores, progresso_esperado

SEG = date(2026, 11, 23)  # segunda-feira


def ativ(qtd=1000, ini=0, fim=4, realizados=(), **kw):
    a = Atividade(descricao="x", unidade="t", qtd_planejada=qtd,
                  inicio_planejado=date(2026, 11, 23 + ini), fim_planejado=date(2026, 11, 23 + fim), **kw)
    for dia, q in realizados:
        a.apontamentos.append(Apontamento(data=date(2026, 11, 23 + dia), quantidade=q))
    return a


def ref(dia):
    return date(2026, 11, 23 + dia)


def test_progresso_esperado_linear_e_inclusivo():
    ini, fim = SEG, ref(4)  # 5 dias
    assert progresso_esperado(ini, fim, ini) == 0
    assert progresso_esperado(ini, fim, ref(1)) == 0.2
    assert progresso_esperado(ini, fim, fim) == 0.8
    assert progresso_esperado(ini, fim, ref(5)) == 1


def test_nao_iniciada_antes_do_inicio():
    assert calcular_situacao(ativ(ini=2, fim=4), ref(0)).status == "nao_iniciada"


def test_no_prazo_dentro_da_tolerancia():
    a = ativ(realizados=[(0, 200), (1, 180)])  # 38% vs esperado 40%
    assert calcular_situacao(a, ref(2)).status == "no_prazo"


def test_atrasada_por_desvio():
    s = calcular_situacao(ativ(realizados=[(0, 100)]), ref(2))  # 10% vs 40%
    assert s.status == "atrasada"
    assert s.desvio == -0.3
    assert s.qtd_esperada == 400


def test_atrasada_por_prazo_vencido():
    s = calcular_situacao(ativ(realizados=[(0, 900)]), ref(7))
    assert s.status == "atrasada"
    assert s.dias_atraso == 3
    assert s.impacto_meta == -100


def test_adiantada():
    assert calcular_situacao(ativ(realizados=[(0, 600)]), ref(1)).status == "adiantada"


def test_adiantada_quando_comeca_antes_do_previsto():
    assert calcular_situacao(ativ(ini=3, fim=4, realizados=[(1, 50)]), ref(2)).status == "adiantada"


def test_concluida_por_quantidade_e_com_atraso():
    s = calcular_situacao(ativ(fim=1, realizados=[(0, 500), (3, 500)]), ref(5))
    assert s.status == "concluida"
    assert s.concluida_com_atraso and s.dias_atraso == 2


def test_concluida_por_fim_real_sem_quantidade():
    a = ativ(qtd=0, fim_real=ref(1))
    s = calcular_situacao(a, ref(2))
    assert s.status == "concluida" and s.progresso_real == 1


def test_progresso_manual_para_atividade_sem_quantidade():
    a = ativ(qtd=0, progresso_manual=10)
    assert calcular_situacao(a, ref(3)).status == "atrasada"   # 10% vs 60%


def test_projecao_no_ritmo_atual():
    s = calcular_situacao(ativ(realizados=[(0, 100), (1, 100)]), ref(2))  # 100/dia * 5 dias
    assert s.projecao == 500
    assert s.impacto_meta == -500


def test_aderencia_nao_premia_excesso():
    adiantada = ativ(realizados=[(0, 1000)])
    atrasada = ativ(realizados=[(0, 100)])
    # esperado em ref(2) = 40%: notas 1.0 (limitada) e 0.25
    assert aderencia([adiantada, atrasada], ref(2)) == 0.625


def test_indicadores_separam_unidades():
    a1 = ativ(realizados=[(0, 100)], tipo="Perfuração")
    a1.unidade = "m"
    a2 = ativ(realizados=[(0, 100)], tipo="Perfuração")
    a1.id, a2.id = 1, 2
    ind = indicadores([a1, a2], ref(1))
    assert {(p["tipo"], p["unidade"]) for p in ind["producao"]} == {("Perfuração", "m"), ("Perfuração", "t")}
