"""Popula o banco com uma semana de planejamento de exemplo (semana atual).

Uso:  python -m app.seed          (adiciona)
      python -m app.seed --limpar (apaga tudo antes)
"""
import sys
from datetime import date, timedelta

from sqlalchemy import delete

from .database import SessionLocal, init_db
from .models import Apontamento, Atividade


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
            db.execute(delete(Apontamento))
            db.execute(delete(Atividade))
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


if __name__ == "__main__":
    popular(limpar="--limpar" in sys.argv)
