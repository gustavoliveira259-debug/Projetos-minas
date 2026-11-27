import { api } from './api.js';
import { estado, periodo, atualizar } from './app.js';
import { formAtividade, modalApontamento } from './modais.js';
import { STATUS, badge, esc, fmtData, fmtNum, fmtPct, fmtPP, semanaParaIntervalo, toISO } from './util.js';

const filtro = { busca: '', frente: '', tipo: '', status: '' };
let ordem = { campo: 'inicio_planejado', dir: 1 };

const COLUNAS = [
  ['codigo', 'Código'], ['descricao', 'Atividade'], ['frente', 'Frente'], ['tipo', 'Tipo'],
  ['equipamento', 'Equip.'], ['responsavel', 'Responsável'], ['inicio_planejado', 'Início'], ['fim_planejado', 'Fim'],
  ['qtd_planejada', 'Planejado', 'num'], ['qtd_realizada', 'Realizado', 'num'],
  ['progresso', 'Progresso', 'num'], ['desvio', 'Desvio', 'num'], ['status', 'Situação'],
];

const valor = (a, campo) => ({
  progresso: a.situacao.progresso_real,
  desvio: a.situacao.desvio,
  status: Object.keys(STATUS).indexOf(a.situacao.status),
}[campo] ?? a[campo] ?? '');

export async function renderAtividades(main) {
  const [todas, opcoes] = await Promise.all([api.atividades(periodo()), api.filtros()]);

  main.innerHTML = `
    <div class="cabecalho-pagina">
      <div><h1>Atividades</h1><p class="mudo" id="contagem"></p></div>
      <button class="btn primario" id="nova">+ Nova atividade</button>
    </div>
    <div class="filtros">
      <label class="busca">Buscar<input type="search" id="f-busca" placeholder="Descrição, código, equipamento, responsável…" value="${esc(filtro.busca)}"></label>
      <label>Frente<select id="f-frente"><option value="">Todas</option>${opcoes.frentes.map((f) => `<option ${f === filtro.frente ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select></label>
      <label>Tipo<select id="f-tipo"><option value="">Todos</option>${opcoes.tipos.map((t) => `<option ${t === filtro.tipo ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
      <label>Situação<select id="f-status"><option value="">Todas</option>${Object.entries(STATUS).map(([k, s]) => `<option value="${k}" ${k === filtro.status ? 'selected' : ''}>${s.rotulo}</option>`).join('')}</select></label>
    </div>
    <div class="tabela-rolagem"><table class="tabela" id="tab">
      <thead><tr>${COLUNAS.map(([k, t, cls]) => `<th class="${cls || ''} ordenavel" data-campo="${k}" aria-sort="${ordem.campo === k ? (ordem.dir > 0 ? 'ascending' : 'descending') : 'none'}">${t}${ordem.campo === k ? (ordem.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}<th></th></tr></thead>
      <tbody></tbody>
    </table></div>`;

  const corpo = main.querySelector('tbody');
  const pintar = () => {
    const q = filtro.busca.toLowerCase();
    const lista = todas
      .filter((a) => (!filtro.frente || a.frente === filtro.frente)
        && (!filtro.tipo || a.tipo === filtro.tipo)
        && (!filtro.status || a.situacao.status === filtro.status)
        && (!q || [a.codigo, a.descricao, a.equipamento, a.responsavel, a.frente].some((v) => (v || '').toLowerCase().includes(q))))
      .sort((x, y) => {
        const a = valor(x, ordem.campo); const b = valor(y, ordem.campo);
        return (a > b ? 1 : a < b ? -1 : 0) * ordem.dir;
      });
    main.querySelector('#contagem').textContent = `${lista.length} de ${todas.length} atividade${todas.length === 1 ? '' : 's'} no período`;
    corpo.innerHTML = lista.map((a) => {
      const s = a.situacao;
      return `<tr data-id="${a.id}">
        <td class="cod">${esc(a.codigo || '')}</td>
        <td>${esc(a.descricao)}${a.observacoes ? `<small class="mudo bloco">${esc(a.observacoes)}</small>` : ''}
          ${a.predecessoras.length ? `<small class="mudo bloco dep">↳ depende de ${a.predecessoras.map((p) => esc(p.codigo || p.descricao)).join(', ')}</small>` : ''}</td>
        <td>${esc(a.frente || '')}</td><td>${esc(a.tipo || '')}</td><td>${esc(a.equipamento || '')}</td>
        <td>${a.responsavel ? `<span class="pessoa">${esc(a.responsavel)}</span>` : '<span class="mudo">—</span>'}</td>
        <td>${fmtData(a.inicio_planejado)}</td><td>${fmtData(a.fim_planejado)}</td>
        <td class="num">${a.qtd_planejada ? `${fmtNum(a.qtd_planejada)} ${esc(a.unidade)}` : '—'}</td>
        <td class="num">${a.qtd_planejada ? `${fmtNum(s.qtd_realizada)} ${esc(a.unidade)}` : '—'}</td>
        <td class="num"><span class="mini-barra"><span class="st-${s.status}" style="width:${Math.min(s.progresso_real, 1) * 100}%"></span></span>${fmtPct(s.progresso_real)}</td>
        <td class="num ${s.desvio < 0 ? 'txt-atrasada' : ''}">${s.status === 'concluida' ? '—' : fmtPP(s.desvio)}</td>
        <td>${badge(s.status)}${s.dias_atraso ? `<small class="mudo bloco">${s.dias_atraso} dia${s.dias_atraso > 1 ? 's' : ''} ${s.status === 'concluida' ? 'após o prazo' : 'vencida'}</small>` : ''}</td>
        <td class="acoes"><button class="btn mini" data-acao="apontar">Andamento</button><button class="btn mini texto" data-acao="editar">Editar</button></td>
      </tr>`;
    }).join('') || `<tr><td colspan="${COLUNAS.length + 1}" class="vazio-celula">Nenhuma atividade encontrada.</td></tr>`;
  };
  pintar();

  const porId = new Map(todas.map((a) => [String(a.id), a]));
  corpo.addEventListener('click', (e) => {
    const b = e.target.closest('[data-acao]');
    if (!b) return;
    const a = porId.get(b.closest('tr').dataset.id);
    if (b.dataset.acao === 'apontar') modalApontamento(a, atualizar);
    else formAtividade(a, atualizar);
  });
  main.querySelectorAll('th.ordenavel').forEach((th) => th.addEventListener('click', () => {
    const c = th.dataset.campo;
    ordem = { campo: c, dir: ordem.campo === c ? -ordem.dir : 1 };
    renderAtividades(main);
  }));
  main.querySelector('#f-busca').addEventListener('input', (e) => { filtro.busca = e.target.value; pintar(); });
  for (const k of ['frente', 'tipo', 'status']) {
    main.querySelector(`#f-${k}`).addEventListener('change', (e) => { filtro[k] = e.target.value; pintar(); });
  }
  main.querySelector('#nova').onclick = () => {
    const ini = estado.todas ? new Date() : semanaParaIntervalo(estado.semana).inicio;
    formAtividade(null, atualizar, { inicio_planejado: toISO(ini), fim_planejado: toISO(ini) });
  };
}
