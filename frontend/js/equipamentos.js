import { api } from './api.js';
import { estado, periodo, atualizar } from './app.js';
import { abrir, modalApontamento } from './modais.js';
import {
  STATUS, addDias, badge, esc, esconderTooltip, fmtData, fmtDataHora, fmtDataLonga, fmtHoras, fmtNum, fmtPct,
  hojeISO, mostrarTooltip, paraDataHoraLocal, parseDataHora, parseISO, toast,
} from './util.js';

export const STATUS_EQ = {
  operando: { rotulo: 'Em operação', icone: '●' },
  disponivel: { rotulo: 'Disponível', icone: '○' },
  manutencao: { rotulo: 'Em manutenção', icone: '!' },
  parado: { rotulo: 'Parado', icone: '‖' },
  inativo: { rotulo: 'Inativo', icone: '–' },
};
const TIPOS_PARADA = {
  corretiva: { rotulo: 'Corretiva', dica: 'Quebra / falha — reduz a disponibilidade' },
  preventiva: { rotulo: 'Preventiva', dica: 'Manutenção programada — reduz a disponibilidade' },
  operacional: { rotulo: 'Operacional', dica: 'Sem operador, clima, sem frente — reduz só a utilização' },
};
const PREV = {
  vencida: { rotulo: 'Vencida', cls: 'txt-atrasada' },
  proxima: { rotulo: 'Próxima', cls: 'txt-parado' },
  ok: { rotulo: 'Em dia', cls: 'txt-concluida' },
  sem_dados: { rotulo: '—', cls: 'mudo' },
};
const CATEGORIAS = ['Escavadeira', 'Caminhão', 'Perfuratriz', 'Pá carregadeira', 'Motoniveladora',
  'Trator de esteira', 'Caminhão-pipa', 'Retroescavadeira'];

const filtro = { categoria: '', busca: '' };

const badgeEq = (st) => {
  const s = STATUS_EQ[st];
  return `<span class="badge eq-${st}"><i aria-hidden="true">${s.icone}</i>${s.rotulo}</span>`;
};
const nivelDF = (df, meta) => (df == null ? '' : df >= meta ? 'bom' : df >= meta - 0.1 ? 'alerta' : 'critico');

export async function renderEquipamentos(main) {
  const p = periodo();
  const dados = await api.painelFrota(p);
  const r = dados.resumo;

  if (!r.total) {
    main.innerHTML = `<div class="cabecalho-pagina"><div><h1>Equipamentos</h1></div></div>
      <div class="vazio"><strong>Nenhum equipamento cadastrado.</strong>
        <p>Cadastre a frota para acompanhar disponibilidade, manutenções e o impacto delas no planejamento.</p>
        <p style="margin-top:14px; display:flex; gap:8px; justify-content:center">
          <button class="btn primario" id="sinc">Cadastrar a partir das atividades</button>
          <button class="btn" id="novo">+ Equipamento</button></p>
        <p class="mudo">A primeira opção cria um equipamento para cada código citado no campo "Equipamento" das atividades (ex.: CM-07/08/09).</p>
      </div>`;
    main.querySelector('#sinc').onclick = sincronizar;
    main.querySelector('#novo').onclick = () => formEquipamento(null, dados);
    return;
  }

  const c = r.contagem;
  const semanaInteira = estado.todas ? ' (semana da data de referência)' : '';
  main.innerHTML = `<div class="pg-equip">
    <div class="cabecalho-pagina">
      <div><h1>Equipamentos</h1>
        <p class="mudo">${fmtDataLonga(dados.inicio)} a ${fmtDataLonga(dados.fim)}${semanaInteira} · situação em ${fmtDataLonga(dados.data_referencia)}</p></div>
      <div class="acoes-topo">
        <button class="btn" id="sinc" title="Cadastra os códigos citados nas atividades que ainda não existem">↻ Importar das atividades</button>
        <button class="btn" id="novo">+ Equipamento</button>
        <button class="btn primario" id="nova-parada">Registrar parada</button>
      </div>
    </div>

    <section class="kpis">
      <article class="kpi destaque ${nivelDF(r.df_media, 0.85)}">
        <h2>Disponibilidade física</h2>
        <p class="valor">${fmtPct(r.df_media)}</p>
        <p class="mudo">Média da frota até a data · prevista p/ o período: <b>${fmtPct(r.df_prevista)}</b>${r.uf_media != null ? ` · UF ${fmtPct(r.uf_media)}` : ''}</p>
      </article>
      ${kpi('Em operação', c.operando, 'eq-operando', `${c.disponivel} disponíve${c.disponivel === 1 ? 'l' : 'is'} sem atividade`)}
      ${kpi('Em manutenção', c.manutencao, 'eq-manutencao', `${c.parado} parado${c.parado === 1 ? '' : 's'} (operacional)`)}
      ${kpi('Horas de manutenção', fmtNum(r.horas_corretiva + r.horas_preventiva), '', `${fmtNum(r.horas_corretiva)} h corretiva · ${fmtNum(r.horas_preventiva)} h preventiva`)}
      ${kpi('Preventivas', r.preventivas_vencidas, r.preventivas_vencidas ? 'eq-manutencao' : '', `vencida${r.preventivas_vencidas === 1 ? '' : 's'} · ${r.preventivas_proximas} próxima${r.preventivas_proximas === 1 ? '' : 's'}`)}
      ${kpi('Risco ao plano', r.atividades_afetadas, r.atividades_afetadas ? 'eq-manutencao' : 'eq-disponivel', `atividade${r.atividades_afetadas === 1 ? '' : 's'} com equipamento parado`)}
    </section>

    <section class="cartao">
      <div class="titulo-linha">
        <h2>Uso da frota no período</h2>
        <ul class="legenda">
          <li><span class="amostra uso-ativ"></span>Atividade planejada</li>
          <li><span class="amostra pd-corretiva"></span>Corretiva</li>
          <li><span class="amostra pd-preventiva"></span>Preventiva</li>
          <li><span class="amostra pd-operacional"></span>Parada operacional</li>
          <li><span class="amostra pd-aberta"></span>Em aberto</li>
        </ul>
      </div>
      <div class="filtros">
        <label>Categoria<select id="f-cat"><option value="">Todas</option>${dados.por_categoria.map((g) => `<option ${g.categoria === filtro.categoria ? 'selected' : ''}>${esc(g.categoria)}</option>`).join('')}</select></label>
        <label class="busca">Buscar<input type="search" id="f-busca" placeholder="Código, modelo, frente…" value="${esc(filtro.busca)}"></label>
      </div>
      <div class="linha-tempo" id="linha-tempo"></div>
    </section>

    <div class="duas-colunas">
      <section class="cartao largo">
        <h2>Possíveis atrasos por equipamento parado ${dados.conflitos.length ? `<span class="contador st-atrasada">${dados.conflitos.length}</span>` : ''}</h2>
        <p class="mudo">Atividades ainda não concluídas cujo equipamento tem parada dentro da janela planejada. A perda de capacidade divide as horas paradas pelo total de horas-equipamento previstas na atividade.</p>
        ${tabelaConflitos(dados.conflitos)}
      </section>
      <section class="cartao">
        <h2>Disponibilidade por categoria</h2>
        <ul class="barras-h larga">
          ${dados.por_categoria.map((g) => `
            <li data-dica="${esc(g.categoria)}: ${g.equipamentos} equipamento(s), ${g.em_manutencao} em manutenção agora${g.uf != null ? `, UF ${fmtPct(g.uf)}` : ''}">
              <span class="rot">${esc(g.categoria)} <small class="mudo">(${g.equipamentos})</small></span>
              <span class="trilho"><span class="b ${nivelDF(g.df, 0.85)}" style="width:${(g.df ?? 0) * 100}%"></span><span class="meta-df" style="left:85%"></span></span>
              <span class="val">${fmtPct(g.df)}</span>
              ${g.em_manutencao ? `<span class="txt-atrasada mini-tag">${g.em_manutencao} manut.</span>` : '<span></span>'}
            </li>`).join('')}
        </ul>
        <p class="mudo nota">Traço vertical = meta de 85%.</p>
        ${dados.nao_cadastrados.length ? `<p class="aviso">Equipamentos citados nas atividades e não cadastrados: <b>${dados.nao_cadastrados.map(esc).join(', ')}</b>.
          <button class="btn mini" id="sinc2">Cadastrar</button></p>` : ''}
      </section>
    </div>

    <section class="cartao">
      <h2>Frota</h2>
      <div class="tabela-rolagem"><table class="tabela" id="tab-frota">
        <thead><tr><th>Código</th><th>Categoria</th><th>Frente</th><th>Situação</th><th class="barra-col-df">DF até a data</th>
          <th class="num">DF prevista</th><th class="num">UF</th><th class="num">Corretiva</th><th class="num">Preventiva</th>
          <th class="num">MTTR</th><th>Próx. preventiva</th><th class="num">Ativ.</th><th></th></tr></thead>
        <tbody></tbody>
      </table></div>
    </section></div>`;

  const porId = new Map(dados.equipamentos.map((e) => [String(e.id), e]));
  const pintar = () => {
    const q = filtro.busca.toLowerCase();
    const lista = dados.equipamentos.filter((e) => (!filtro.categoria || (e.categoria || 'Sem categoria') === filtro.categoria)
      && (!q || [e.codigo, e.descricao, e.frente, e.categoria].some((v) => (v || '').toLowerCase().includes(q))));
    main.querySelector('#linha-tempo').innerHTML = linhaTempo(lista, dados);
    main.querySelector('#tab-frota tbody').innerHTML = lista.map(linhaFrota).join('')
      || '<tr><td colspan="13" class="vazio-celula">Nenhum equipamento encontrado.</td></tr>';
    ligarDicas(main.querySelector('#linha-tempo'), porId);
  };
  pintar();

  main.querySelector('#f-cat').onchange = (e) => { filtro.categoria = e.target.value; pintar(); };
  main.querySelector('#f-busca').oninput = (e) => { filtro.busca = e.target.value; pintar(); };
  main.querySelector('#sinc').onclick = sincronizar;
  main.querySelector('#sinc2')?.addEventListener('click', sincronizar);
  main.querySelector('#novo').onclick = () => formEquipamento(null, dados);
  main.querySelector('#nova-parada').onclick = () => formParada(null, dados);

  main.querySelectorAll('.barras-h [data-dica]').forEach((el) => {
    el.addEventListener('pointermove', (ev) => mostrarTooltip(esc(el.dataset.dica), ev.clientX, ev.clientY));
    el.addEventListener('pointerleave', esconderTooltip);
  });

  main.querySelector('.pg-equip').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-acao]');
    if (!b) return;
    const e = porId.get(b.dataset.eq);
    const acao = b.dataset.acao;
    if (acao === 'parada') formParada(e, dados);
    else if (acao === 'horas') formHoras(e);
    else if (acao === 'editar') formEquipamento(e, dados);
    else if (acao === 'ativ') abrirAtividade(b.dataset.ativ);
  });
}

async function abrirAtividade(id) {
  const a = (await api.atividades(periodo())).find((x) => String(x.id) === String(id));
  if (a) modalApontamento(a, atualizar);
  else toast('Atividade fora do período selecionado.', 'info');
}

async function sincronizar() {
  try {
    const r = await api.sincronizarEquipamentos();
    toast(r.criados.length ? `${r.criados.length} equipamento(s) cadastrado(s): ${r.criados.join(', ')}.` : 'Nenhum equipamento novo encontrado nas atividades.', r.criados.length ? 'ok' : 'info');
    atualizar();
  } catch (e) { toast(e.message, 'erro'); }
}

function kpi(titulo, valor, cls, sub) {
  return `<article class="kpi ${cls ? `borda-eq ${cls}` : ''}"><h2>${titulo}</h2>
    <p class="valor">${valor}</p><p class="mudo">${sub}</p></article>`;
}

// ---------- linha do tempo ----------

function corte(dados) {
  const ref = dados.data_referencia;
  const fimRef = addDias(parseISO(ref), 1);
  return ref === hojeISO() ? new Date() : fimRef;
}

function linhaTempo(lista, dados) {
  const ini = parseISO(dados.inicio);
  const fim = addDias(parseISO(dados.fim), 1);
  const total = fim - ini;
  const dias = Math.round(total / 86400000);
  const pos = (d) => Math.min(Math.max((d - ini) / total, 0), 1) * 100;
  const agora = corte(dados);
  const xAgora = pos(agora);

  const cab = Array.from({ length: dias }, (_, i) => {
    const d = addDias(ini, i);
    const fds = d.getDay() === 0 || d.getDay() === 6;
    return `<span class="lt-dia ${fds ? 'fds' : ''}"><b>${d.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '')}</b> ${fmtData(d)}</span>`;
  }).join('');

  const linhas = lista.map((e) => {
    const ativs = e.atividades.map((a) => {
      const l = pos(parseISO(a.inicio_planejado)); const r = pos(addDias(parseISO(a.fim_planejado), 1));
      if (r <= 0 || l >= 100) return '';
      return `<span class="lt-ativ st-${a.status}" style="left:${l}%;width:${r - l}%" data-tip="ativ" data-eq="${e.id}" data-id="${a.id}"></span>`;
    }).join('');
    const pds = e.paradas.map((p) => {
      const pi = parseDataHora(p.inicio);
      const aberta = !p.fim;
      const pf = aberta ? agora : parseDataHora(p.fim);
      const l = pos(pi); const r = pos(pf < pi ? pi : pf);
      const cont = aberta ? `<span class="lt-parada pd-aberta" style="left:${r}%;width:${100 - r}%" aria-hidden="true"></span>` : '';
      return `<span class="lt-parada pd-${p.tipo}" style="left:${l}%;width:${Math.max(r - l, 0.4)}%" data-tip="parada" data-eq="${e.id}" data-id="${p.id}"></span>${cont}`;
    }).join('');
    return `<div class="lt-linha">
      <div class="lt-rotulo">
        <button class="lt-nome" data-acao="parada" data-eq="${e.id}" title="Registrar parada">${esc(e.codigo)}<small class="mudo">${esc(e.categoria || '')}</small></button>
        ${badgeEq(e.status)}
      </div>
      <div class="lt-faixa" style="--dias:${dias}">${ativs}${pds}
        ${xAgora > 0 && xAgora < 100 ? `<span class="lt-agora" style="left:${xAgora}%"></span>` : ''}</div>
    </div>`;
  }).join('');

  return `<div class="lt-linha lt-cab"><div class="lt-rotulo">Equipamento</div><div class="lt-faixa lt-dias">${cab}</div></div>${linhas
    || '<p class="mudo" style="padding:12px">Nenhum equipamento encontrado.</p>'}`;
}

function ligarDicas(el, porId) {
  el.querySelectorAll('[data-tip]').forEach((n) => {
    const e = porId.get(n.dataset.eq);
    let html = '';
    if (n.dataset.tip === 'ativ') {
      const a = e.atividades.find((x) => String(x.id) === n.dataset.id);
      html = `<div class="dica-tit"><strong>${esc(a.codigo || '')} ${esc(a.descricao)}</strong>${badge(a.status)}</div>
        <table><tr><th>Equipamento</th><td>${esc(e.codigo)}</td></tr><tr><th>Frente</th><td>${esc(a.frente || '—')}</td></tr>
        <tr><th>Planejado</th><td>${fmtDataLonga(a.inicio_planejado)} a ${fmtDataLonga(a.fim_planejado)}</td></tr></table>`;
      n.addEventListener('click', () => abrirAtividade(a.id));
    } else {
      const p = e.paradas.find((x) => String(x.id) === n.dataset.id);
      const dur = p.fim ? (parseDataHora(p.fim) - parseDataHora(p.inicio)) / 3600000 : null;
      html = `<div class="dica-tit"><strong>${esc(e.codigo)} · ${TIPOS_PARADA[p.tipo].rotulo}</strong>${!p.fim ? '<span class="badge eq-manutencao">Em aberto</span>' : ''}</div>
        <table><tr><th>Início</th><td>${fmtDataHora(p.inicio)}</td></tr>
        <tr><th>Fim</th><td>${p.fim ? fmtDataHora(p.fim) : 'ainda parado'}</td></tr>
        ${dur != null ? `<tr><th>Duração</th><td>${fmtHoras(dur)}</td></tr>` : ''}
        ${p.motivo ? `<tr><th>Motivo</th><td>${esc(p.motivo)}</td></tr>` : ''}</table>`;
      n.addEventListener('click', () => formParada(e, null, p));
    }
    n.addEventListener('pointermove', (ev) => mostrarTooltip(html, ev.clientX, ev.clientY));
    n.addEventListener('pointerleave', esconderTooltip);
  });
}

// ---------- tabelas ----------

function tabelaConflitos(conf) {
  if (!conf.length) return '<p class="ok-msg">✓ Nenhuma atividade do período depende de equipamento parado.</p>';
  return `<table class="tabela">
    <thead><tr><th>Atividade</th><th>Equip.</th><th>Parada</th><th class="num">Horas</th><th class="num">Perda de capacidade</th>
      <th class="num">Produção em risco</th><th></th></tr></thead>
    <tbody>${conf.map((c) => `<tr>
      <td><span class="cod">${esc(c.codigo_atividade || '')}</span> ${esc(c.descricao)}
        <small class="mudo bloco">${esc(c.frente || '')} · ${fmtData(c.inicio_planejado)} a ${fmtData(c.fim_planejado)} · ${STATUS[c.status_atividade].rotulo}</small></td>
      <td><b>${esc(c.equipamento)}</b>${c.equipamentos_na_atividade > 1 ? `<small class="mudo bloco">1 de ${c.equipamentos_na_atividade}</small>` : ''}</td>
      <td><span class="tag-parada pd-${c.tipo_parada}">${TIPOS_PARADA[c.tipo_parada].rotulo}</span>
        ${c.em_aberto ? '<span class="txt-atrasada mini-tag"> em aberto</span>' : c.programada ? '<span class="mudo mini-tag"> programada</span>' : ''}
        <small class="mudo bloco">${fmtDataHora(c.parada_inicio)} → ${c.parada_fim ? fmtDataHora(c.parada_fim) : '?'}${c.motivo ? ` · ${esc(c.motivo)}` : ''}</small></td>
      <td class="num">${fmtNum(c.horas_sobrepostas)} h</td>
      <td class="num ${c.perda_capacidade >= 0.15 ? 'txt-atrasada' : ''}">${fmtPct(c.perda_capacidade)}</td>
      <td class="num">${c.producao_em_risco ? `${fmtNum(c.producao_em_risco)} ${esc(c.unidade)}` : '—'}</td>
      <td><button class="btn mini" data-acao="ativ" data-eq="${c.equipamento_id}" data-ativ="${c.atividade_id}">Atividade</button></td>
    </tr>`).join('')}</tbody></table>`;
}

function linhaFrota(e) {
  const pv = e.preventiva;
  const prevTxt = pv.estado === 'sem_dados'
    ? (pv.programada_para ? `programada ${fmtDataHora(pv.programada_para)}` : '—')
    : `<b class="${PREV[pv.estado].cls}">${PREV[pv.estado].rotulo}</b> <span class="mudo">${pv.restante_h > 0 ? `faltam ${fmtNum(pv.restante_h)} h` : `${fmtNum(-pv.restante_h)} h além`}</span>
       ${pv.programada_para ? `<small class="mudo bloco">programada ${fmtDataHora(pv.programada_para)}</small>` : ''}`;
  const df = e.df ?? 0;
  return `<tr class="${e.ativo ? '' : 'inativo'}">
    <td><b>${esc(e.codigo)}</b>${e.descricao ? `<small class="mudo bloco">${esc(e.descricao)}</small>` : ''}</td>
    <td>${esc(e.categoria || '—')}</td><td>${esc(e.frente || '—')}</td>
    <td>${badgeEq(e.status)}${e.parada_atual ? `<small class="mudo bloco">${esc(e.parada_atual.motivo || TIPOS_PARADA[e.parada_atual.tipo].rotulo)} · desde ${fmtDataHora(e.parada_atual.inicio)}</small>` : ''}</td>
    <td class="barra-col-df"><span class="df-cel"><span class="trilho"><span class="b ${nivelDF(e.df, e.meta_df)}" style="width:${df * 100}%"></span><span class="meta-df" style="left:${e.meta_df * 100}%" title="Meta ${fmtPct(e.meta_df)}"></span></span><b>${fmtPct(e.df)}</b></span></td>
    <td class="num ${e.df_prevista != null && e.df_prevista < e.meta_df ? 'txt-atrasada' : ''}">${fmtPct(e.df_prevista)}${e.horas_manutencao_programada ? `<small class="mudo bloco">+${fmtNum(e.horas_manutencao_programada)} h prog.</small>` : ''}</td>
    <td class="num">${fmtPct(e.uf)}${e.horas_trabalhadas != null ? `<small class="mudo bloco">${fmtNum(e.horas_trabalhadas)} h trab.</small>` : ''}</td>
    <td class="num">${fmtHoras(e.horas_corretiva)}${e.corretivas ? `<small class="mudo bloco">${e.corretivas} falha${e.corretivas > 1 ? 's' : ''}</small>` : ''}</td>
    <td class="num">${fmtHoras(e.horas_preventiva)}</td>
    <td class="num">${fmtHoras(e.mttr_h)}</td>
    <td>${prevTxt}</td>
    <td class="num">${e.atividades.length || '—'}</td>
    <td class="acoes"><button class="btn mini" data-acao="parada" data-eq="${e.id}">Parada</button><button class="btn mini texto" data-acao="horas" data-eq="${e.id}">Horas</button><button class="btn mini texto" data-acao="editar" data-eq="${e.id}">Editar</button></td>
  </tr>`;
}

// ---------- formulários ----------

const erroForm = (m, e) => { const el = m.querySelector('.erro-form'); el.textContent = e.message; el.hidden = false; };
const numOuNulo = (v) => (String(v).trim() === '' ? null : Number(v));

async function formEquipamento(eq, dados) {
  const e = eq || { meta_df: 0.85, ativo: true };
  const v = (k) => esc(e[k] ?? '');
  const filtros = await api.filtros().catch(() => ({ frentes: [] }));
  const cats = [...new Set([...CATEGORIAS, ...(dados?.por_categoria || []).map((c) => c.categoria)])];
  const m = abrir(`
    <form method="dialog" class="form">
      <header><h2>${eq ? `Editar ${esc(eq.codigo)}` : 'Novo equipamento'}</h2>
        <button type="button" class="btn icone" data-fechar aria-label="Fechar">×</button></header>
      <div class="grade">
        <label>Código*<input name="codigo" required maxlength="50" value="${v('codigo')}" placeholder="ex.: ES-01"></label>
        <label class="c2">Descrição / modelo<input name="descricao" maxlength="120" value="${v('descricao')}" placeholder="ex.: Escavadeira CAT 374F"></label>
        <label>Categoria<input name="categoria" list="dl-cat" value="${v('categoria')}"></label>
        <label>Frente (alocação)<input name="frente" list="dl-fr" value="${v('frente')}"></label>
        <label title="Disponibilidade física mínima esperada">Meta de DF (%)<input name="meta_df" type="number" min="0" max="100" step="1" value="${Math.round((e.meta_df ?? 0.85) * 100)}"></label>
        <label>Intervalo da preventiva (h)<input name="intervalo_preventiva_h" type="number" min="1" step="any" value="${v('intervalo_preventiva_h')}" placeholder="ex.: 250"></label>
        <label>Horímetro na última preventiva<input name="horimetro_ultima_preventiva" type="number" min="0" step="any" value="${v('horimetro_ultima_preventiva')}"></label>
        <label class="chk"><input type="checkbox" name="ativo" ${e.ativo ? 'checked' : ''}> Ativo na frota</label>
        <label class="c3">Observações<textarea name="observacoes" rows="2">${v('observacoes')}</textarea></label>
      </div>
      <datalist id="dl-cat">${cats.map((c) => `<option value="${esc(c)}">`).join('')}</datalist>
      <datalist id="dl-fr">${(filtros.frentes || []).map((c) => `<option value="${esc(c)}">`).join('')}</datalist>
      <p class="erro-form" hidden></p>
      <footer>
        ${eq ? '<button type="button" class="btn perigo" id="excluir">Excluir</button>' : ''}
        <span class="esp"></span>
        <button type="button" class="btn texto" data-fechar>Cancelar</button>
        <button type="submit" class="btn primario">Salvar</button>
      </footer>
    </form>`);
  const f = m.querySelector('form');
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    const d = {
      codigo: f.codigo.value.trim(), descricao: f.descricao.value.trim() || null,
      categoria: f.categoria.value.trim() || null, frente: f.frente.value.trim() || null,
      meta_df: (numOuNulo(f.meta_df.value) ?? 85) / 100,
      intervalo_preventiva_h: numOuNulo(f.intervalo_preventiva_h.value),
      horimetro_ultima_preventiva: numOuNulo(f.horimetro_ultima_preventiva.value),
      ativo: f.ativo.checked, observacoes: f.observacoes.value.trim() || null,
    };
    try {
      if (eq) await api.atualizarEquipamento(eq.id, d); else await api.criarEquipamento(d);
      m.close(); toast(eq ? 'Equipamento atualizado.' : 'Equipamento cadastrado.'); atualizar();
    } catch (err) { erroForm(m, err); }
  };
  m.querySelector('#excluir')?.addEventListener('click', async () => {
    if (!confirm(`Excluir ${eq.codigo} com todas as paradas e horas registradas?`)) return;
    await api.excluirEquipamento(eq.id); m.close(); toast('Equipamento excluído.'); atualizar();
  });
}

/** Registrar (ou editar) parada. Sem `eq`, pede para escolher o equipamento. */
async function formParada(eq, dados, parada = null) {
  const lista = eq ? [eq] : dados.equipamentos;
  const historico = eq ? (await api.paradas(eq.id)).slice().reverse() : [];
  const agora = new Date(); agora.setMinutes(Math.floor(agora.getMinutes() / 15) * 15, 0, 0);
  const p = parada || { tipo: 'corretiva', inicio: paraDataHoraLocal(agora), fim: null };
  const m = abrir(`
    <form method="dialog" class="form">
      <header><h2>${parada ? 'Editar parada' : 'Registrar parada'}${eq ? ` · ${esc(eq.codigo)}` : ''}</h2>
        <button type="button" class="btn icone" data-fechar aria-label="Fechar">×</button></header>
      <div class="grade">
        ${eq ? '' : `<label>Equipamento*<select name="equipamento" required><option value="">Selecione…</option>
          ${lista.map((e) => `<option value="${e.id}">${esc(e.codigo)} — ${esc(e.categoria || '')}</option>`).join('')}</select></label>`}
        <fieldset class="c3 tipos-parada"><legend>Tipo*</legend>
          ${Object.entries(TIPOS_PARADA).map(([k, t]) => `<label class="opcao-tipo pd-${k}"><input type="radio" name="tipo" value="${k}" ${p.tipo === k ? 'checked' : ''}>
            <span><b>${t.rotulo}</b><small>${t.dica}</small></span></label>`).join('')}
        </fieldset>
        <label>Início*<input name="inicio" type="datetime-local" required value="${String(p.inicio).slice(0, 16)}"></label>
        <label>Fim<input name="fim" type="datetime-local" value="${p.fim ? String(p.fim).slice(0, 16) : ''}"></label>
        <label class="chk"><input type="checkbox" name="aberta" ${p.fim ? '' : 'checked'}> Ainda parado (sem previsão)</label>
        <label class="c2">Motivo<input name="motivo" maxlength="255" value="${esc(p.motivo || '')}" placeholder="ex.: vazamento hidráulico, troca de pneu, preventiva 250 h"></label>
        <label title="Na preventiva, atualiza o contador da próxima">Horímetro<input name="horimetro" type="number" min="0" step="any" value="${p.horimetro ?? ''}"></label>
      </div>
      <p class="mudo nota">Para programar uma manutenção futura, informe início e fim previstos — ela entra na DF prevista e nos conflitos com o planejamento.</p>
      <p class="erro-form" hidden></p>
      <footer>
        ${parada ? '<button type="button" class="btn perigo" id="excluir">Excluir</button>' : ''}
        <span class="esp"></span>
        <button type="button" class="btn texto" data-fechar>Cancelar</button>
        <button type="submit" class="btn primario">Salvar</button>
      </footer>
      ${eq && !parada ? `<h3>Paradas registradas</h3>${historico.length ? `<table class="tabela compacta"><thead><tr><th>Tipo</th><th>Início</th><th>Fim</th><th class="num">Duração</th><th>Motivo</th><th></th></tr></thead><tbody>
        ${historico.slice(0, 15).map((h) => `<tr><td><span class="tag-parada pd-${h.tipo}">${TIPOS_PARADA[h.tipo].rotulo}</span></td>
          <td>${fmtDataHora(h.inicio)}</td><td>${h.fim ? fmtDataHora(h.fim) : '<b class="txt-atrasada">em aberto</b>'}</td>
          <td class="num">${h.fim ? fmtHoras((parseDataHora(h.fim) - parseDataHora(h.inicio)) / 3600000) : '—'}</td>
          <td>${esc(h.motivo || '')}</td>
          <td class="acoes">${h.fim ? '' : `<button type="button" class="btn mini" data-encerrar="${h.id}">Encerrar agora</button>`}
            <button type="button" class="btn mini texto" data-editar="${h.id}">Editar</button></td></tr>`).join('')}
      </tbody></table>` : '<p class="mudo">Nenhuma parada registrada.</p>'}` : ''}
    </form>`);
  const f = m.querySelector('form');
  const sincAberta = () => { f.fim.disabled = f.aberta.checked; if (f.aberta.checked) f.fim.value = ''; };
  f.aberta.onchange = sincAberta;
  f.fim.oninput = () => { if (f.fim.value) f.aberta.checked = false; };
  sincAberta();
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    const id = eq ? eq.id : Number(f.equipamento.value);
    const d = {
      tipo: f.tipo.value, inicio: f.inicio.value, fim: f.aberta.checked ? null : (f.fim.value || null),
      motivo: f.motivo.value.trim() || null, horimetro: numOuNulo(f.horimetro.value),
    };
    try {
      if (parada) await api.atualizarParada(parada.id, d); else await api.criarParada(id, d);
      m.close(); toast(parada ? 'Parada atualizada.' : 'Parada registrada.'); atualizar();
    } catch (err) { erroForm(m, err); }
  };
  m.querySelector('#excluir')?.addEventListener('click', async () => {
    if (!confirm('Excluir esta parada?')) return;
    await api.excluirParada(parada.id); m.close(); toast('Parada excluída.'); atualizar();
  });
  m.querySelectorAll('[data-encerrar]').forEach((b) => b.addEventListener('click', async () => {
    try {
      await api.atualizarParada(b.dataset.encerrar, { fim: paraDataHoraLocal(new Date()) });
      m.close(); toast('Parada encerrada — equipamento liberado.'); atualizar();
    } catch (err) { erroForm(m, err); }
  }));
  m.querySelectorAll('[data-editar]').forEach((b) => b.addEventListener('click', () => {
    formParada(eq, dados, historico.find((h) => String(h.id) === b.dataset.editar));
  }));
}

async function formHoras(eq) {
  const historico = (await api.horas(eq.id)).slice().reverse();
  const ultimo = historico.find((h) => h.horimetro != null)?.horimetro;
  const m = abrir(`
    <form method="dialog" class="form">
      <header><h2>Horas trabalhadas · ${esc(eq.codigo)}</h2>
        <button type="button" class="btn icone" data-fechar aria-label="Fechar">×</button></header>
      <div class="grade">
        <label>Data*<input name="data" type="date" required value="${hojeISO()}"></label>
        <label>Horas trabalhadas*<input name="horas" type="number" min="0" max="24" step="0.1" required></label>
        <label>Horímetro${ultimo != null ? ` <span class="mudo">(último ${fmtNum(ultimo)})</span>` : ''}<input name="horimetro" type="number" min="0" step="any"></label>
        <label class="c3">Observação<input name="obs" maxlength="255" placeholder="Turnos, operador…"></label>
      </div>
      <p class="mudo nota">As horas trabalhadas calculam a utilização (UF); o horímetro controla quando vence a próxima preventiva.</p>
      <p class="erro-form" hidden></p>
      <footer><span class="esp"></span>
        <button type="button" class="btn texto" data-fechar>Fechar</button>
        <button type="submit" class="btn primario">Registrar</button></footer>
      <h3>Histórico</h3>
      ${historico.length ? `<table class="tabela compacta"><thead><tr><th>Data</th><th class="num">Horas</th><th class="num">Horímetro</th><th>Observação</th><th></th></tr></thead><tbody>
        ${historico.slice(0, 20).map((h) => `<tr><td>${fmtDataLonga(h.data)}</td><td class="num">${fmtNum(h.horas_trabalhadas)}</td>
          <td class="num">${h.horimetro != null ? fmtNum(h.horimetro) : '—'}</td><td>${esc(h.observacao || '')}</td>
          <td><button type="button" class="btn icone mini" data-del="${h.id}" aria-label="Excluir registro">×</button></td></tr>`).join('')}
      </tbody></table>` : '<p class="mudo">Nenhum registro.</p>'}
    </form>`);
  const f = m.querySelector('form');
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api.registrarHoras(eq.id, { data: f.data.value, horas_trabalhadas: Number(f.horas.value),
        horimetro: numOuNulo(f.horimetro.value), observacao: f.obs.value.trim() || null });
      m.close(); toast('Horas registradas.'); atualizar();
    } catch (err) { erroForm(m, err); }
  };
  m.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Excluir este registro?')) return;
    await api.excluirHoras(b.dataset.del); m.close(); toast('Registro excluído.'); atualizar();
  }));
}
