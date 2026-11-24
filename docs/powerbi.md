# Integração com Power BI

O MinePlan Control expõe tabelas planas, prontas para o Power BI, em `/api/powerbi/`:

| Feed | Conteúdo | Granularidade |
|---|---|---|
| `atividades` | Cadastro + situação calculada (status, progresso, desvio, projeção, impacto na meta, semana ISO) | 1 linha por atividade |
| `apontamentos` | Produção realizada lançada | 1 linha por apontamento (dia) |
| `plano-diario` | Quantidade planejada distribuída linearmente por dia | 1 linha por atividade × dia |
| `indicadores` | Planejado, esperado, realizado, projeção e aderência por tipo/unidade | 1 linha por tipo + unidade |

Parâmetros opcionais: `inicio`, `fim` (AAAA-MM-DD), `data_ref` (data de referência dos cálculos) e `formato=csv` (CSV com `;` em UTF-8).

## Conectando (Power BI Desktop)

1. **Obter dados → Web → Avançado**.
2. URL: `http://<servidor>:8000/api/powerbi/atividades`.
3. Se o servidor tiver `MINEPLAN_POWERBI_TOKEN`, adicione o cabeçalho HTTP `X-API-Key` com o token.
4. Repita para `apontamentos` e `plano-diario`.

Ou cole no **Editor Avançado** do Power Query:

```powerquery
let
    Base = "http://servidor:8000/api/powerbi/",
    Fonte = Json.Document(Web.Contents(Base, [RelativePath = "atividades" /*, Headers = [#"X-API-Key" = "TOKEN"] */])),
    Tabela = Table.FromRecords(Fonte),
    Tipos = Table.TransformColumnTypes(Tabela, {
        {"inicio_planejado", type date}, {"fim_planejado", type date},
        {"inicio_real", type date}, {"fim_real", type date},
        {"qtd_planejada", type number}, {"qtd_realizada", type number}, {"qtd_esperada", type number},
        {"saldo", type number}, {"projecao", type number}, {"impacto_meta", type number},
        {"progresso_real", Percentage.Type}, {"progresso_esperado", Percentage.Type}, {"desvio", type number},
        {"dias_atraso", Int64.Type}
    })
in
    Tipos
```

`RelativePath` permite que a atualização agendada funcione no Power BI Service (por meio de um gateway on-premises, já que o servidor fica na rede interna).

## Modelo sugerido

- `Calendario` (tabela de datas) → `apontamentos[data]` e `plano-diario[data]`.
- `atividades[id]` 1 → * `apontamentos[atividade_id]` e `plano-diario[atividade_id]`.

## Medidas DAX sugeridas

```dax
Planejado (dia) = SUM ( 'plano-diario'[qtd_planejada_dia] )
Realizado = SUM ( apontamentos[quantidade] )
Planejado acumulado =
    CALCULATE ( [Planejado (dia)], FILTER ( ALL ( Calendario[Data] ), Calendario[Data] <= MAX ( Calendario[Data] ) ) )
Realizado acumulado =
    CALCULATE ( [Realizado], FILTER ( ALL ( Calendario[Data] ), Calendario[Data] <= MAX ( Calendario[Data] ) ) )
Atingimento = DIVIDE ( [Realizado], [Planejado (dia)] )
Atividades atrasadas = CALCULATE ( COUNTROWS ( atividades ), atividades[status] = "atrasada" )
Impacto previsto na meta = SUM ( atividades[impacto_meta] )
```

> Filtre sempre por **unidade** (t, m, m³…) ao somar quantidades: tipos diferentes usam unidades diferentes.

Com o *Planejado acumulado* e o *Realizado acumulado* por dia, você monta a curva S planejado × realizado da semana.
