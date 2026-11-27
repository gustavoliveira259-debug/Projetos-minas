import { api } from './api.js';
import { estado, periodo, atualizar } from './app.js';
import { avisarEmpurradas, formAtividade, modalApontamento } from './modais.js';
import {
  STATUS, addDias, badge, difDias, esc, esconderTooltip, fmtData, fmtDataLonga, fmtNum, fmtPct, fmtPP,
  mostrarTooltip, parseISO, semanaParaIntervalo, toISO, toast,
} from './util.js';

const filtro = { frente: '', tipo: '', agrupar: true };
const recolhidos = new Set();
const LARG_ROTULO = 300;
const DIAS_SEMANA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

export async function renderGantt(main) {
  const p = periodo();
  const [ats, opcoes] = await Promise.all([
    api.atividades({ ...p, frente: filtro.frente, tipo: filtro.tipo }),
    api.filtros(),
  ]);

  main.innerHTML = `
    <div class="cabecalho-pagina">
      <div><h1>Cronograma</h1>
        <p class="mudo">Arraste uma barra para mover a atividade, ou as bordas para mudar início e fim. Clique na barra para registrar andamento e no nome para editar.</p></div>
      <button class="btn primario" id="nova">+ Nova atividade</button>
    </div>
    <div class="filtros">
      <label>Frente<select id="f-frente"><option value="">Todas</option>${opcoes.frentes.map((f) => `<option ${f === filtro.frente ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select></label>
      <label>Tipo<select id="f-tipo"><option value="">Todos</option>${opcoes.tipos.map((t) => `<option ${t === filtro.tipo ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
      <label class="chk"><input type="checkbox" id="f-agrupar" ${filtro.agrupar ? 'checked' : ''}> Agrupar por frente</label>
      <span class="esp"></span>
      <ul class="legenda" aria-label="Legenda">
        ${Object.entries(STATUS).map(([k, s]) => `<li><span class="amostra st-${k}"></span>${s.rotulo}</li>`).join('')}
        <li><span class="amostra esperado"></span>Progresso esperado</li>
        <li><span class="amostra real"></span>Execução real</li>
        <li><span class="amostra dep"></span>Dependência</li>
      </ul>
    </div>
    <div class="gantt" id="gantt"></div>`;

  main.querySelector('#nova').onclick = () => novaAtividade();
  main.querySelector('#f-frente').onchange = (e) => { filtro.frente = e.target.value; atualizar(); };
  main.querySelector('#f-tipo').onchange = (e) => { filtro.tipo = e.target.value; atualizar(); };
  main.querySelector('#f-agrupar').onchange = (e) => { filtro.agrupar = e.target.checked; atualizar(); };

  const el = main.querySelector('#gantt');
  if (!ats.length) {
    el.innerHTML = `<div class="vazio"><strong>Nenhuma atividade neste período.</strong>
      <p>Cadastre uma atividade ou <a href="#/importar">importe a planilha de planejamento</a>.</p></div>`;
    return;
  }
  desenhar(el, ats);
}

function novaAtividade(dia) {
  const base = dia || (estado.todas ? new Date() : semanaParaIntervalo(estado.semana).inicio);
  formAtividade(null, atualizar, {
    inicio_planejado: toISO(base), fim_planejado: toISO(base),
    frente: filtro.frente || undefined, tipo: filtro.tipo || undefined,
  });
}

function intervalo(ats) {
  let ini, fim;
  if (!estado.todas) ({ inicio: ini, fim } = semanaParaIntervalo(estado.semana));
  for (const a of ats) {
    const ai = parseISO(a.inicio_planejado);
    const af = parseISO(a.fim_planejado);
    const ri = a.inicio_real && parseISO(a.inicio_real);
    if (!ini || ai < ini) ini = ai;
    if (ri && ri < ini) ini = ri;
    if (!fim || af > fim) fim = af;
  }
  return { ini, fim, dias: difDias(ini, fim) + 1 };
}

function desenhar(el, ats) {
  const { ini, dias } = intervalo(ats);
  const larguraUtil = Math.max(el.clientWidth - LARG_ROTULO - 2, 300);
  const dw = Math.max(34, Math.min(170, Math.floor(larguraUtil / dias)));
  const larg = dias * dw;
  const ref = parseISO(estado.dataRef);
  const xRef = difDias(ini, ref) * dw;
  const refVisivel = xRef >= 0 && xRef <= larg;

  // Cabeçalho de dias
  let cab = '';
  for (let i = 0; i < dias; i++) {
    const d = addDias(ini, i);
    const fds = d.getDay() === 0 || d.getDay() === 6;
    const eRef = toISO(d) === estado.dataRef;
    cab += `<div class="g-dia ${fds ? 'fds' : ''} ${eRef ? 'ref' : ''}" style="width:${dw}px" data-dia="${toISO(d)}">
      <span>${DIAS_SEMANA[d.getDay()]}</span><b>${fmtData(d)}</b></div>`;
  }
  const fundo = `background-size:${dw}px 100%`;

  const grupos = new Map();
  for (const a of ats) {
    const chave = filtro.agrupar ? (a.frente || 'Sem frente') : '';
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(a);
  }

  let linhas = '';
  for (const [nome, lista] of grupos) {
    if (filtro.agrupar) {
      const atras = lista.filter((a) => a.situacao.status === 'atrasada').length;
      const fechado = recolhidos.has(nome);
      linhas += `<div class="g-linha g-grupo" data-grupo="${esc(nome)}">
        <div class="g-rotulo"><button class="btn-grupo" aria-expanded="${!fechado}">${fechado ? '▸' : '▾'} ${esc(nome)}</button>
          <span class="mudo">${lista.length} ativ.${atras ? ` · <span class="txt-atrasada">${atras} atrasada${atras > 1 ? 's' : ''}</span>` : ''}</span></div>
        <div class="g-faixa" style="width:${larg}px;${fundo}"></div></div>`;
      if (fechado) continue;
    }
    for (const a of lista) linhas += linha(a, ini, dw, larg, ref, fundo);
  }

  el.innerHTML = `
    <div class="g-rolagem">
      <div class="g-linha g-cabecalho">
        <div class="g-rotulo"><span>Atividade</span><span class="mudo">Progresso</span></div>
        <div class="g-faixa g-dias" style="width:${larg}px">${cab}</div>
      </div>
      ${linhas}
      ${refVisivel ? `<div class="g-hoje" style="left:${LARG_ROTULO + xRef}px" title="Data de referência"></div>` : ''}
    </div>`;

  const linhaRef = el.querySelector('.g-hoje');
  if (linhaRef) linhaRef.style.height = `${el.querySelector('.g-rolagem').scrollHeight}px`;

  desenharDependencias(el, ats);
  const porId = new Map(ats.map((a) => [String(a.id), a]));
  ligarEventos(el, porId, ini, dw);
}

function linha(a, ini, dw, larg, ref, fundo) {
  const s = a.situacao;
  const i0 = parseISO(a.inicio_planejado);
  const dur = difDias(i0, parseISO(a.fim_planejado)) + 1;
  const x = difDias(ini, i0) * dw;
  const w = dur * dw;
  const prog = Math.min(s.progresso_real, 1);
  const rotulo = w > 70 ? `${fmtPct(s.progresso_real)}` : '';

  // Execução real: do início real até a conclusão (ou até a data de referência)
  let real = '';
  if (a.inicio_real) {
    const ri = parseISO(a.inicio_real);
    const rf = a.fim_real ? addDias(parseISO(a.fim_real), 1) : (s.status === 'concluida' && s.data_conclusao ? addDias(parseISO(s.data_conclusao), 1) : ref);
    const rx = difDias(ini, ri) * dw;
    const rw = Math.max(difDias(ri, rf) * dw, 4);
    real = `<div class="g-real" style="left:${rx}px;width:${rw}px"></div>`;
  }
  const marcaEsperado = s.status !== 'concluida' && s.progresso_esperado > 0 && s.progresso_esperado < 1
    ? `<i class="g-esperado" style="left:${s.progresso_esperado * 100}%"></i>` : '';

  return `<div class="g-linha" data-id="${a.id}">
    <div class="g-rotulo">
      <button class="g-nome" data-editar="${a.id}" title="Editar atividade">
        <span class="cod">${esc(a.codigo || '')}</span> ${esc(a.descricao)}
        <small class="mudo">${esc([a.tipo, a.equipamento].filter(Boolean).join(' · '))}${a.responsavel ? `${a.tipo || a.equipamento ? ' · ' : ''}<span class="pessoa">${esc(a.responsavel)}</span>` : ''}</small>
      </button>
      <span class="g-prog txt-${s.status}" title="${STATUS[s.status].rotulo}">${STATUS[s.status].icone} ${fmtPct(s.progresso_real)}</span>
    </div>
    <div class="g-faixa" style="width:${larg}px;${fundo}">
      <div class="g-barra st-${s.status}" data-id="${a.id}" style="left:${x}px;width:${w}px" tabindex="0"
           aria-label="${esc(a.descricao)}: ${STATUS[s.status].rotulo}, ${fmtPct(s.progresso_real)}">
        <span class="g-preench" style="width:${prog * 100}%"></span>
        ${marcaEsperado}
        <span class="g-txt">${[rotulo, w > 150 && a.responsavel ? esc(a.responsavel) : ''].filter(Boolean).join(' · ')}</span>
        <span class="g-alca e" data-alca="e"></span><span class="g-alca d" data-alca="d"></span>
      </div>
      ${real}
    </div>
  </div>`;
}

function dica(a) {
  const s = a.situacao;
  const un = esc(a.unidade);
  const temQtd = a.qtd_planejada > 0;
  return `<div class="dica-tit"><strong>${esc(a.codigo || '')} ${esc(a.descricao)}</strong>${badge(s.status)}</div>
    <table>
      <tr><th>Planejado</th><td>${fmtDataLonga(a.inicio_planejado)} → ${fmtDataLonga(a.fim_planejado)}</td></tr>
      <tr><th>Real</th><td>${a.inicio_real ? fmtDataLonga(a.inicio_real) : '—'} → ${a.fim_real ? fmtDataLonga(a.fim_real) : (s.status === 'concluida' ? fmtDataLonga(s.data_conclusao) : 'em aberto')}</td></tr>
      ${temQtd ? `<tr><th>Quantidade</th><td>${fmtNum(s.qtd_realizada)} de ${fmtNum(a.qtd_planejada)} ${un}</td></tr>` : ''}
      <tr><th>Progresso</th><td>${fmtPct(s.progresso_real)} <span class="mudo">(esperado ${fmtPct(s.progresso_esperado)}, ${fmtPP(s.desvio)})</span></td></tr>
      ${temQtd && s.status !== 'concluida' ? `<tr><th>Projeção</th><td>${fmtNum(s.projecao)} ${un} <span class="${s.impacto_meta < 0 ? 'txt-atrasada' : 'mudo'}">(${s.impacto_meta > 0 ? '+' : ''}${fmtNum(s.impacto_meta)} ${un} na meta)</span></td></tr>` : ''}
      ${s.dias_atraso ? `<tr><th>Atraso</th><td class="txt-atrasada">${s.dias_atraso} dia${s.dias_atraso > 1 ? 's' : ''}</td></tr>` : ''}
      ${a.frente ? `<tr><th>Frente</th><td>${esc(a.frente)}</td></tr>` : ''}
      ${a.equipamento ? `<tr><th>Equipamento</th><td>${esc(a.equipamento)}</td></tr>` : ''}
      ${a.responsavel ? `<tr><th>Responsável</th><td>${esc(a.responsavel)}</td></tr>` : ''}
      ${a.predecessoras.length ? `<tr><th>Depende de</th><td>${a.predecessoras.map(refCurta).join(', ')}</td></tr>` : ''}
      ${a.sucessoras.length ? `<tr><th>Dependentes</th><td>${a.sucessoras.map(refCurta).join(', ')}</td></tr>` : ''}
    </table>`;
}

const refCurta = (r) => `${esc(r.codigo || r.descricao)} <span class="mudo">(${fmtData(r.inicio_planejado)}–${fmtData(r.fim_planejado)})</span>`;

/** Setas fim → início entre predecessora e dependente (só as duas visíveis no cronograma). */
function desenharDependencias(el, ats) {
  const rolagem = el.querySelector('.g-rolagem');
  const base = rolagem.getBoundingClientRect();
  const caixa = (id) => {
    const b = rolagem.querySelector(`.g-barra[data-id="${id}"]`);
    if (!b) return null;
    const r = b.getBoundingClientRect();
    const x = r.left - base.left + rolagem.scrollLeft;
    const y = r.top - base.top + rolagem.scrollTop;
    return { x1: x, x2: x + r.width, y: y + r.height / 2, alto: r.height };
  };
  let caminhos = '';
  for (const a of ats) {
    const d = caixa(a.id);
    if (!d) continue;
    for (const p of a.predecessoras) {
      const o = caixa(p.id);
      if (!o) continue;
      const xs = o.x2;
      const xe = d.x1;
      // Sai pela direita da principal, desce e entra pela esquerda da dependente.
      const desvio = xe - xs >= 14
        ? `H${xs + 7} V${d.y} H${xe}`
        : `h7 V${d.y - Math.sign(d.y - o.y || 1) * (d.alto / 2 + 6)} H${xe - 8} V${d.y} H${xe}`;
      caminhos += `<path d="M${xs} ${o.y} ${desvio}" marker-end="url(#seta-dep)"/>`;
    }
  }
  if (!caminhos) return;
  rolagem.insertAdjacentHTML('beforeend', `<svg class="g-deps" width="${rolagem.scrollWidth}" height="${rolagem.scrollHeight}" aria-hidden="true">
    <defs><marker id="seta-dep" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M0 0 L8 4 L0 8 Z"/></marker></defs>${caminhos}</svg>`);
}

function ligarEventos(el, porId, ini, dw) {
  el.querySelectorAll('.btn-grupo').forEach((b) => b.addEventListener('click', () => {
    const g = b.closest('.g-grupo').dataset.grupo;
    if (recolhidos.has(g)) recolhidos.delete(g); else recolhidos.add(g);
    desenhar(el, [...porId.values()]);
  }));
  el.querySelectorAll('[data-editar]').forEach((b) => b.addEventListener('click', () => {
    formAtividade(porId.get(b.dataset.editar), atualizar);
  }));
  el.querySelectorAll('.g-dias .g-dia').forEach((d) => d.addEventListener('dblclick', () => novaAtividade(parseISO(d.dataset.dia))));

  el.querySelectorAll('.g-barra').forEach((barra) => {
    const a = porId.get(barra.dataset.id);
    barra.addEventListener('pointerenter', (e) => mostrarTooltip(dica(a), e.clientX, e.clientY));
    barra.addEventListener('pointermove', (e) => { if (!arraste) mostrarTooltip(dica(a), e.clientX, e.clientY); });
    barra.addEventListener('pointerleave', () => { if (!arraste) esconderTooltip(); });
    barra.addEventListener('focus', () => {
      const r = barra.getBoundingClientRect();
      mostrarTooltip(dica(a), r.left, r.bottom);
    });
    barra.addEventListener('blur', esconderTooltip);
    barra.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); modalApontamento(a, atualizar); }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        const n = e.key === 'ArrowLeft' ? -1 : 1;
        salvarDatas(a, e.shiftKey ? 0 : n, n);  // Shift+seta altera só o fim
      }
    });
    barra.addEventListener('pointerdown', (e) => iniciarArraste(e, barra, a, dw));
  });
}

let arraste = null;

function iniciarArraste(e, barra, a, dw) {
  if (e.button !== 0) return;
  e.preventDefault();
  barra.setPointerCapture(e.pointerId);
  const modo = e.target.dataset.alca === 'e' ? 'inicio' : e.target.dataset.alca === 'd' ? 'fim' : 'mover';
  arraste = { x0: e.clientX, left: parseFloat(barra.style.left), width: parseFloat(barra.style.width), dIni: 0, dFim: 0, moveu: false };
  barra.classList.add('arrastando');

  const mover = (ev) => {
    const dx = ev.clientX - arraste.x0;
    if (Math.abs(dx) > 3) arraste.moveu = true;
    const n = Math.round(dx / dw);
    const dur = Math.round(arraste.width / dw);
    let { left, width } = arraste;
    if (modo === 'mover') { arraste.dIni = n; arraste.dFim = n; left += n * dw; }
    if (modo === 'inicio') { const k = Math.min(n, dur - 1); arraste.dIni = k; arraste.dFim = 0; left += k * dw; width -= k * dw; }
    if (modo === 'fim') { const k = Math.max(n, 1 - dur); arraste.dIni = 0; arraste.dFim = k; width += k * dw; }
    barra.style.left = `${left}px`;
    barra.style.width = `${width}px`;
    const ni = addDias(parseISO(a.inicio_planejado), arraste.dIni);
    const nf = addDias(parseISO(a.fim_planejado), arraste.dFim);
    if (arraste.moveu) mostrarTooltip(`<strong>${fmtDataLonga(ni)} → ${fmtDataLonga(nf)}</strong>`, ev.clientX, ev.clientY);
  };
  const soltar = async () => {
    barra.removeEventListener('pointermove', mover);
    barra.removeEventListener('pointerup', soltar);
    barra.removeEventListener('pointercancel', soltar);
    barra.classList.remove('arrastando');
    const { dIni, dFim, moveu } = arraste;
    arraste = null;
    esconderTooltip();
    if (!moveu) { modalApontamento(a, atualizar); return; }
    if (dIni || dFim) await salvarDatas(a, dIni, dFim);
    else atualizar();
  };
  barra.addEventListener('pointermove', mover);
  barra.addEventListener('pointerup', soltar);
  barra.addEventListener('pointercancel', soltar);
}

async function salvarDatas(a, dIni, dFim) {
  const ini = addDias(parseISO(a.inicio_planejado), dIni);
  const fim = addDias(parseISO(a.fim_planejado), dFim);
  if (fim < ini) return;
  try {
    const resp = await api.atualizar(a.id, { inicio_planejado: toISO(ini), fim_planejado: toISO(fim) });
    toast(`${a.codigo || a.descricao}: ${fmtDataLonga(ini)} → ${fmtDataLonga(fim)}`);
    avisarEmpurradas(resp);
  } catch (e) {
    toast(e.message, 'erro');
  }
  atualizar();
}
