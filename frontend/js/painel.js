import { api } from './api.js';
import { periodo, atualizar } from './app.js';
import { modalApontamento } from './modais.js';
import { STATUS, esc, esconderTooltip, fmtDataLonga, fmtNum, fmtPct, fmtPP, mostrarTooltip } from './util.js';

const ORDEM = ['concluida', 'adiantada', 'no_prazo', 'nao_iniciada', 'atrasada'];

export async function renderPainel(main) {
  const p = periodo();
  const ind = await api.indicadores(p);
  const c = ind.contagem;

  if (!ind.total) {
    main.innerHTML = `<div class="cabecalho-pagina"><div><h1>Painel</h1></div></div>
      <div class="vazio"><strong>Nenhuma atividade planejada neste período.</strong>
      <p><a href="#/importar">Importe a planilha de planejamento</a> ou <a href="#/atividades">cadastre atividades</a>.</p></div>`;
    return;
  }

  const ader = ind.aderencia;
  const classeAder = ader == null ? '' : ader >= 0.9 ? 'bom' : ader >= 0.75 ? 'alerta' : 'critico';

  main.innerHTML = `
    <div class="cabecalho-pagina">
      <div><h1>Painel</h1><p class="mudo">Situação em ${fmtDataLonga(ind.data_referencia)} · tolerância de desvio ±${fmtPct(ind.tolerancia)}</p></div>
    </div>

    <section class="kpis">
      <article class="kpi destaque ${classeAder}">
        <h2>Aderência ao plano</h2>
        <p class="valor">${ader == null ? '—' : fmtPct(ader)}</p>
        <p class="mudo">${ader == null ? 'Nenhuma atividade deveria ter avançado ainda' : 'Média do realizado ÷ esperado até a data, limitada a 100% por atividade'}</p>
      </article>
      ${kpi('Atividades', ind.total, '', 'no período')}
      ${kpi('Concluídas', c.concluida, 'concluida', pct(c.concluida, ind.total))}
      ${kpi('Atrasadas', c.atrasada, 'atrasada', pct(c.atrasada, ind.total))}
      ${kpi('Adiantadas', c.adiantada, 'adiantada', pct(c.adiantada, ind.total))}
      ${kpi('No prazo', c.no_prazo, 'no_prazo', `${c.nao_iniciada} não iniciada${c.nao_iniciada === 1 ? '' : 's'}`)}
    </section>

    <section class="cartao">
      <h2>Distribuição por situação</h2>
      <div class="segmentos" role="img" aria-label="${ORDEM.map((k) => `${STATUS[k].rotulo}: ${c[k]}`).join(', ')}">
        ${ORDEM.filter((k) => c[k]).map((k) => `<span class="seg st-${k}" style="flex:${c[k]}" data-dica="${STATUS[k].rotulo}: ${c[k]} (${pct(c[k], ind.total)})"></span>`).join('')}
      </div>
      <ul class="legenda">${ORDEM.map((k) => `<li><span class="amostra st-${k}"></span>${STATUS[k].rotulo} <b>${c[k]}</b></li>`).join('')}</ul>
    </section>

    <div class="duas-colunas">
      <section class="cartao largo">
        <h2>Produção: planejado × realizado</h2>
        <p class="mudo">Barra = realizado; traço = esperado até a data; trilho = meta do período. Projeção considera o ritmo atual de cada atividade.</p>
        <table class="tabela producao">
          <thead><tr><th>Tipo</th><th class="barra-col">Andamento</th><th class="num">Realizado</th><th class="num">Meta</th>
            <th class="num">Aderência até a data</th><th class="num">Projeção</th><th class="num">Impacto na meta</th></tr></thead>
          <tbody>${ind.producao.map(linhaProducao).join('') || '<tr><td colspan="7" class="mudo">Sem atividades com quantidade.</td></tr>'}</tbody>
        </table>
      </section>

      <section class="cartao">
        <h2>Aderência por frente</h2>
        <ul class="barras-h">
          ${ind.frentes.map((f) => `
            <li data-dica="${esc(f.frente)}: ${f.atividades} atividades, ${f.concluidas} concluídas, ${f.atrasadas} atrasadas">
              <span class="rot">${esc(f.frente)}</span>
              <span class="trilho"><span class="b ${nivel(f.aderencia)}" style="width:${(f.aderencia ?? 0) * 100}%"></span></span>
              <span class="val">${f.aderencia == null ? '—' : fmtPct(f.aderencia)}</span>
              ${f.atrasadas ? `<span class="txt-atrasada mini-tag">${f.atrasadas} atras.</span>` : '<span></span>'}
            </li>`).join('')}
        </ul>
      </section>
    </div>

    <section class="cartao">
      <h2>Atividades atrasadas ${ind.alertas.length ? `<span class="contador st-atrasada">${ind.alertas.length}</span>` : ''}</h2>
      ${ind.alertas.length ? `<table class="tabela">
        <thead><tr><th>Atividade</th><th>Frente</th><th>Fim planejado</th><th class="num">Desvio</th><th class="num">Dias vencida</th>
          <th class="num">Saldo</th><th class="num">Impacto previsto</th><th></th></tr></thead>
        <tbody>${ind.alertas.map((a) => `<tr>
          <td><span class="cod">${esc(a.codigo || '')}</span> ${esc(a.descricao)}</td><td>${esc(a.frente || '—')}</td>
          <td>${fmtDataLonga(a.fim_planejado)}</td><td class="num txt-atrasada">${fmtPP(a.desvio)}</td>
          <td class="num">${a.dias_atraso || '—'}</td><td class="num">${fmtNum(a.saldo)} ${esc(a.unidade)}</td>
          <td class="num ${a.impacto_meta < 0 ? 'txt-atrasada' : ''}">${a.impacto_meta ? `${fmtNum(a.impacto_meta)} ${esc(a.unidade)}` : '—'}</td>
          <td><button class="btn mini" data-apontar="${a.id}">Atualizar</button></td></tr>`).join('')}</tbody>
      </table>` : '<p class="ok-msg">✓ Nenhuma atividade atrasada no período.</p>'}
    </section>`;

  main.querySelectorAll('[data-dica]').forEach((el) => {
    el.addEventListener('pointermove', (e) => mostrarTooltip(esc(el.dataset.dica), e.clientX, e.clientY));
    el.addEventListener('pointerleave', esconderTooltip);
  });
  main.querySelectorAll('[data-apontar]').forEach((b) => b.addEventListener('click', async () => {
    const a = (await api.atividades(periodo())).find((x) => String(x.id) === b.dataset.apontar);
    if (a) modalApontamento(a, atualizar);
  }));
}

const pct = (n, t) => (t ? fmtPct(n / t) : '—');
const nivel = (v) => (v == null ? '' : v >= 0.9 ? 'bom' : v >= 0.75 ? 'alerta' : 'critico');

function kpi(titulo, valor, status, sub) {
  return `<article class="kpi ${status ? `borda-${status}` : ''}">
    <h2>${status ? `<i class="txt-${status}" aria-hidden="true">${STATUS[status].icone}</i> ` : ''}${titulo}</h2>
    <p class="valor">${valor}</p><p class="mudo">${sub}</p></article>`;
}

function linhaProducao(p) {
  const max = Math.max(p.planejado, p.realizado, p.projecao, 1);
  const w = (v) => `${Math.min(v / max, 1) * 100}%`;
  const un = esc(p.unidade);
  const dica = `${p.tipo}: realizado ${fmtNum(p.realizado)} ${p.unidade}, esperado até a data ${fmtNum(p.esperado_ate_ref)}, meta ${fmtNum(p.planejado)}, projeção ${fmtNum(p.projecao)}`;
  return `<tr>
    <td><strong>${esc(p.tipo)}</strong> <span class="mudo">(${un})</span></td>
    <td class="barra-col"><span class="bullet" data-dica="${esc(dica)}">
      <span class="trilho" style="width:${w(p.planejado)}"></span>
      <span class="real ${nivel(p.aderencia_ate_ref)}" style="width:${w(p.realizado)}"></span>
      ${p.esperado_ate_ref > 0 ? `<span class="marca" style="left:${w(p.esperado_ate_ref)}"></span>` : ''}
    </span></td>
    <td class="num">${fmtNum(p.realizado)}</td>
    <td class="num">${fmtNum(p.planejado)}</td>
    <td class="num">${p.aderencia_ate_ref == null ? '—' : fmtPct(p.aderencia_ate_ref)}</td>
    <td class="num">${fmtNum(p.projecao)}</td>
    <td class="num ${p.impacto_meta < 0 ? 'txt-atrasada' : 'txt-concluida'}">${p.impacto_meta > 0 ? '+' : ''}${fmtNum(p.impacto_meta)} ${un}</td>
  </tr>`;
}
