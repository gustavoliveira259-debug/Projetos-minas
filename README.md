# MinePlan Control

Sistema web para gerenciamento e acompanhamento do **planejamento semanal de lavra** da BEMISA.

- **Importação de planilhas** (.xlsx/.csv) com prévia, reconhecimento flexível de colunas e modo *mesclar* (atualiza pelo código).
- **Cadastro e edição** de atividades (frente de lavra, tipo, equipamento, quantidade, unidade, datas planejadas e reais).
- **Cronograma (Gantt) interativo**: arraste a barra para mover, arraste as bordas para mudar início/fim, clique para registrar andamento. Pelo teclado: Enter abre o andamento, as setas movem a atividade e Shift+seta altera só o fim.
- **Atualização de andamento** por apontamentos diários de produção, com histórico.
- **Situação automática**: não iniciada, no prazo, adiantada, atrasada e concluída (inclusive "concluída após o prazo").
- **Indicadores**: aderência ao plano, planejado × realizado × esperado por tipo/unidade, projeção no ritmo atual e **impacto previsto na meta**.
- **Exportação para Excel** (Resumo, Atividades, Apontamentos, Indicadores).
- **Integração com Power BI** via feeds JSON/CSV: veja [docs/powerbi.md](docs/powerbi.md).

## Como executar

Requisitos: Python 3.11+.

```powershell
.\iniciar.ps1 -Exemplo     # primeira vez: cria o ambiente, instala dependências e carrega dados de exemplo
.\iniciar.ps1              # nas próximas vezes
```

Acesse http://localhost:8000. A documentação interativa da API fica em http://localhost:8000/docs.

Manualmente:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
cd backend
..\.venv\Scripts\python -m app.seed --limpar     # opcional: dados de exemplo da semana atual
..\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Testes: `cd backend; ..\.venv\Scripts\python -m pytest`

## Regras de cálculo

| Conceito | Regra |
|---|---|
| Duração | Datas diárias e inclusivas (01/12 a 03/12 = 3 dias). |
| Progresso real | Realizado ÷ planejado. Em atividades sem quantidade (ex.: infraestrutura), usa o *progresso manual* (%). |
| Progresso esperado | Dias completos decorridos ÷ duração, na **data de referência**. No 1º dia é 0%; após o fim, 100%. |
| Concluída | Realizado ≥ planejado, *fim real* preenchido ou progresso manual = 100%. É "após o prazo" se concluiu depois do fim planejado. |
| Atrasada | Prazo vencido sem conclusão, **ou** progresso real mais de 10 p.p. abaixo do esperado. |
| Adiantada | Progresso real mais de 10 p.p. acima do esperado, ou produção iniciada antes do início planejado. |
| Aderência ao plano | Média, por atividade, de min(real ÷ esperado, 100%). Não mistura toneladas com metros, e uma atividade adiantada não mascara outra atrasada. |
| Projeção / impacto na meta | Realizado ÷ dias decorridos × duração. Impacto = projeção − planejado (negativo = déficit previsto). |

A tolerância de 10 p.p. pode ser alterada pela variável de ambiente `MINEPLAN_TOLERANCIA` (ex.: `0.05`).

Ao filtrar por semana, entram as atividades planejadas nela **e** as pendências de semanas anteriores que ainda estão abertas (ou que foram concluídas dentro da semana).

A **data de referência** (barra superior) permite ver a situação como estava em outro dia, por exemplo para fechar a semana anterior.

## Formato da planilha

Baixe o modelo em **Importar → Baixar modelo de planilha**. Colunas obrigatórias: *Atividade*, *Início* e *Fim* (ou *Duração*).
Também são reconhecidos nomes alternativos, como *Frente de Lavra*, *Local*, *Cava*, *Término*, *Volume*, *Qtd Planejada*, *Realizado* e *Equipamento*. A linha de cabeçalho é localizada automaticamente nas 15 primeiras linhas, e a aba escolhida é a que mais se parece com um planejamento. Aceita datas DD/MM/AAAA e números no padrão brasileiro (1.234,5).
Uma coluna *Qtd Realizada* vira um apontamento de produção; ao reimportar, só a diferença é lançada.

## Estrutura

```
backend/app/
  main.py          app FastAPI + frontend estático
  models.py        Atividade e Apontamento (SQLAlchemy)
  status.py        regras de situação, aderência e indicadores
  importer.py      leitura de planilhas
  exporter.py      geração de Excel
  routers/         atividades, importação/exportação, Power BI
  seed.py          dados de exemplo
backend/tests/     testes automatizados (pytest)
frontend/          HTML + CSS + JavaScript (sem etapa de build)
```

## Configuração

| Variável | Padrão | Uso |
|---|---|---|
| `MINEPLAN_DB_URL` | SQLite em `backend/data/mineplan.db` | URL SQLAlchemy (ex.: PostgreSQL/SQL Server em produção) |
| `MINEPLAN_TOLERANCIA` | `0.10` | Tolerância de desvio para atrasada/adiantada |
| `MINEPLAN_POWERBI_TOKEN` | — | Se definido, exige o token nos feeds `/api/powerbi/*` |

## Próximos passos sugeridos

- Autenticação de usuários e perfis (planejamento × operação) e trilha de auditoria das alterações.
- Banco corporativo (SQL Server/PostgreSQL) e migrações com Alembic.
- Metas de produção cadastradas separadamente do plano (hoje a meta é a soma do planejado).
- Dependências entre atividades (perfuração → desmonte → carregamento) no Gantt.
