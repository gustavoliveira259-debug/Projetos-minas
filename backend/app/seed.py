"""Popula o banco com uma semana de planejamento de exemplo (semana atual).

Uso:  python -m app.seed                (adiciona atividades e frota)
      python -m app.seed --limpar       (apaga tudo antes)
      python -m app.seed --equipamentos (só a frota, sem mexer nas atividades)
"""
import sys
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select

from .database import SessionLocal, init_db
from .models import Apontamento, Atividade, Equipamento, Parada, RegistroHoras


def popular(limpar: bool = False, hoje: date | None = None):
    init_db()
    hoje = hoje or date.today()
    seg = hoje - timedelta(days=hoje.weekday())
    d = lambda n: seg + timedelta(days=n)  # noqa: E731

    # (código, descrição, tipo, frente, equip., resp., un, qtd, ini, fim, ritmo realizado/dia em fração do plano)
    plano = [
        ("PF-101", "Perfuração banco 820 — malha 4x5", "Perfuração", "Cava Norte", "PF-03", "J. Almeida", "m", 1800, 0, 2, 0.40),
        ("DM-101", "Desmonte banco 820", "Desmonte", "Cava Norte", None, "R. Souza", "t", 60000, 3, 3, None),
        ("CG-101", "Carregamento minério banco 820", "Carregamento", "Cava Norte", "ES-01", "C. Lima", "t", 52000, 3, 6, None),
        ("TR-101", "Transporte minério p/ britagem", "Transporte", "Cava Norte", "CM-07/08/09", "C. Lima", "t", 52000, 3, 6, None),
        ("PF-201", "Perfuração banco 790", "Perfuração", "Cava Sul", "PF-05", "J. Almeida", "m", 1500, 0, 3, 0.18),
        ("PF-091", "Perfuração banco 835 (pendência)", "Perfuração", "Cava Norte", "PF-03", "J. Almeida", "m", 1600, -6, -3, 0.20),
        ("CG-091", "Carregamento estéril banco 835", "Carregamento", "Cava Sul", "ES-02", "M. Ferreira", "t", 40000, -5, -2, 0.22),
        ("CG-201", "Carregamento estéril banco 790", "Carregamento", "Cava Sul", "ES-02", "M. Ferreira", "t", 75000, 0, 4, 0.07),
        ("TR-201", "Transporte estéril p/ PDE 2", "Transporte", "Cava Sul", "CM-10/11", "M. Ferreira", "t", 75000, 0, 4, 0.14),
        ("IN-201", "Drenagem rampa de acesso", "Infraestrutura", "Cava Sul", "MN-02", "P. Rocha", "un", 0, 1, 2, None),
        ("CG-301", "Retomada pilha pulmão", "Carregamento", "Pátio", "PC-01", "A. Dias", "t", 30000, 0, 6, 0.20),
        ("IN-301", "Manutenção de praça de carregamento", "Infraestrutura", "Pátio", "TE-01", "P. Rocha", "un", 0, 0, 1, None),
        ("PF-102", "Perfuração banco 805 (antecipação)", "Perfuração", "Cava Norte", "PF-04", "J. Almeida", "m", 900, 4, 6, None),
    ]

    db = SessionLocal()
    try:
        if limpar:
            for tabela in (Apontamento, Atividade, Parada, RegistroHoras, Equipamento):
                db.execute(delete(tabela))
        for cod, desc, tipo, frente, eq, resp, un, qtd, ini, fim, ritmo in plano:
            a = Atividade(codigo=cod, descricao=desc, tipo=tipo, frente=frente, equipamento=eq, responsavel=resp,
                          unidade=un, qtd_planejada=qtd, inicio_planejado=d(ini), fim_planejado=d(fim))
            if ritmo:
                dia = d(ini)
                while dia < hoje and dia <= d(fim):
                    a.apontamentos.append(Apontamento(data=dia, quantidade=round(qtd * ritmo), observacao="Turnos A+B"))
                    dia += timedelta(days=1)
                if a.apontamentos:
                    a.inicio_real = d(ini)
            db.add(a)
        # Uma tarefa sem quantidade concluída e outra com progresso manual
        db.flush()
        for a in db.query(Atividade).filter(Atividade.codigo.in_(["IN-301", "IN-201"])):
            if a.codigo == "IN-301" and hoje > a.inicio_planejado:
                a.inicio_real, a.fim_real = a.inicio_planejado, a.inicio_planejado
            elif a.codigo == "IN-201":
                a.progresso_manual = 30
        # Conclusão fora do prazo: saldo da semana anterior carregado na segunda-feira
        cg = db.query(Atividade).filter_by(codigo="CG-091").one()
        if hoje > seg:
            cg.apontamentos.append(Apontamento(data=seg, quantidade=round(cg.qtd_planejada - cg.qtd_realizada),
                                               observacao="Saldo da semana anterior"))
        # Antecipação: produção iniciada antes do previsto
        pf = db.query(Atividade).filter_by(codigo="PF-102").one()
        if hoje >= seg:
            pf.apontamentos.append(Apontamento(data=min(hoje, d(3)), quantidade=250, observacao="Sonda liberada antes"))
            pf.inicio_real = min(hoje, d(3))
        db.commit()
        print(f"{len(plano)} atividades de exemplo criadas para a semana de {seg:%d/%m/%Y}.")
    finally:
        db.close()
    popular_equipamentos(hoje=hoje)


def popular_equipamentos(hoje: date | None = None, agora: datetime | None = None):
    """Frota de exemplo com paradas e horas trabalhadas na semana atual. Não duplica códigos existentes."""
    init_db()
    hoje = hoje or date.today()
    agora = agora or datetime.combine(hoje, datetime.now().time())
    seg = hoje - timedelta(days=hoje.weekday())
    dt = lambda dia, hora, minuto=0: datetime.combine(seg + timedelta(days=dia), time(hora, minuto))  # noqa: E731

    # (código, descrição, categoria, frente, intervalo preventiva, horímetro última preventiva, horímetro na segunda)
    frota = [
        ("PF-03", "Perfuratriz Sandvik DX800", "Perfuratriz", "Cava Norte", 250, 3000, 3200),
        ("PF-04", "Perfuratriz Sandvik DX800", "Perfuratriz", "Cava Norte", 250, 4300, 4420),
        ("PF-05", "Perfuratriz Epiroc FlexiROC D65", "Perfuratriz", "Cava Sul", 250, 4800, 4990),
        ("ES-01", "Escavadeira CAT 374F", "Escavadeira", "Cava Norte", 500, 11800, 12010),
        ("ES-02", "Escavadeira Komatsu PC700", "Escavadeira", "Cava Sul", 500, 9400, 9650),
        ("PC-01", "Pá carregadeira CAT 980M", "Pá carregadeira", "Pátio", 500, 7000, 7120),
        ("CM-07", "Caminhão Volvo FMX 500 8x4", "Caminhão", "Cava Norte", 250, 15200, 15300),
        ("CM-08", "Caminhão Volvo FMX 500 8x4", "Caminhão", "Cava Norte", 250, 14900, 15010),
        ("CM-09", "Caminhão Volvo FMX 500 8x4", "Caminhão", "Cava Norte", 250, 13800, 13850),
        ("CM-10", "Caminhão Scania G500 8x4", "Caminhão", "Cava Sul", 250, 8100, 8200),
        ("CM-11", "Caminhão Scania G500 8x4", "Caminhão", "Cava Sul", 250, 7900, 8120),
        ("MN-02", "Motoniveladora CAT 140K", "Motoniveladora", "Cava Sul", 500, 6000, 6100),
        ("TE-01", "Trator de esteira CAT D8T", "Trator de esteira", "Pátio", 500, 10000, 10200),
    ]
    # (código, tipo, início, fim (None = em aberto), motivo)
    paradas = [
        ("CM-08", "corretiva", dt(0, 6), dt(0, 14, 30), "Troca de pneu traseiro"),
        ("CM-10", "operacional", dt(1, 18), dt(2, 6), "Falta de operador no turno C"),
        ("ES-01", "corretiva", dt(1, 9), dt(1, 13), "Mangueira hidráulica rompida"),
        ("ES-02", "corretiva", agora - timedelta(hours=20), None, "Vazamento no cilindro da lança"),
        ("PF-04", "preventiva", dt(5, 7), dt(5, 17), "Preventiva 250 h"),
        ("CM-11", "preventiva", dt(3, 7), dt(3, 15), "Preventiva 250 h + lubrificação"),
        ("PC-01", "preventiva", dt(0, 7), dt(0, 11), "Inspeção semanal"),
    ]

    db = SessionLocal()
    try:
        existentes = set(db.scalars(select(Equipamento.codigo)))
        criados = 0
        for i, (cod, desc, cat, frente, intervalo, ult_prev, horim) in enumerate(frota):
            if cod in existentes:
                continue
            e = Equipamento(codigo=cod, descricao=desc, categoria=cat, frente=frente, meta_df=0.85,
                            intervalo_preventiva_h=intervalo, horimetro_ultima_preventiva=ult_prev)
            for cod_p, tipo, ini, fim, motivo in paradas:
                if cod_p == cod and (tipo == "preventiva" or ini <= agora):
                    e.paradas.append(Parada(tipo=tipo, inicio=ini, fim=fim if not fim or fim <= agora or ini > agora or tipo == "preventiva"
                                            else None, motivo=motivo))
            dia = seg
            while dia < hoje:
                horas = 15 + (i * 3 + dia.weekday() * 5) % 6       # 15 a 20 h/dia, variando por equipamento
                if cod == "ES-02" and dia >= (agora - timedelta(hours=20)).date():
                    horas = 4
                horim += horas
                e.registros_horas.append(RegistroHoras(data=dia, horas_trabalhadas=horas, horimetro=horim,
                                                       observacao="Turnos A+B+C"))
                dia += timedelta(days=1)
            db.add(e)
            criados += 1
        db.commit()
        print(f"{criados} equipamentos de exemplo criados.")
    finally:
        db.close()


if __name__ == "__main__":
    if "--equipamentos" in sys.argv:
        popular_equipamentos()
    else:
        popular(limpar="--limpar" in sys.argv)
