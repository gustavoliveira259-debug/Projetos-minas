import { api } from './api.js';
import { periodo, atualizar } from './app.js';
import { modalApontamento } from './modais.js';
import { STATUS, esc, esconderTooltip, fmtDataLonga, fmtNum, fmtPct, fmtPP, mostrarTooltip } from './util.js';

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

function kpi(titulo, valor, status, sub) {
  return `<article class="kpi ${status ? `borda-${status}` : ''}">
    <h2>${status ? `<i class="txt-${status}" aria-hidden="true">${STATUS[status].icone}</i> ` : ''}${titulo}</h2>
    <p class="valor">${valor}</p><p class="mudo">${sub}</p></article>`;
}
