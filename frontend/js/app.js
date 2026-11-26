import { api } from './api.js';
import { addDias, dataParaSemana, hojeISO, semanaParaIntervalo, toISO, fmtDataLonga, toast } from './util.js';
import { renderPainel } from './painel.js';
import { renderGantt } from './gantt.js';
import { renderAtividades } from './atividades.js';
import { renderImportar } from './importar.js';
import { renderEquipamentos } from './equipamentos.js';

const salvo = JSON.parse(localStorage.getItem('mineplan.periodo') || '{}');

export const estado = {
  semana: salvo.semana || dataParaSemana(new Date()),
  todas: !!salvo.todas,
  dataRef: hojeISO(),
};

/** Parâmetros de período + data de referência usados por todas as consultas. */
export function periodo() {
  const p = { data_ref: estado.dataRef };
  if (!estado.todas) {
    const { inicio, fim } = semanaParaIntervalo(estado.semana);
    p.inicio = toISO(inicio);
    p.fim = toISO(fim);
  }
  return p;
}

const rotas = {
  painel: renderPainel,
  gantt: renderGantt,
  atividades: renderAtividades,
  equipamentos: renderEquipamentos,
  importar: renderImportar,
};

const $ = (id) => document.getElementById(id);
const main = $('conteudo');

export async function atualizar() {
  const rota = (location.hash.replace('#/', '') || 'painel').split('?')[0];
  const render = rotas[rota] || renderPainel;
  document.querySelectorAll('.abas a').forEach((a) => a.classList.toggle('ativa', a.dataset.rota === rota));
  sincronizarBarra();
  try {
    await render(main);
  } catch (e) {
    main.innerHTML = `<div class="vazio erro"><strong>Não foi possível carregar os dados.</strong><p>${e.message}</p>
      <p class="mudo">Verifique se o servidor está em execução.</p></div>`;
  }
}

function sincronizarBarra() {
  $('semana').value = estado.semana;
  $('todas').checked = estado.todas;
  $('data-ref').value = estado.dataRef;
  ['semana', 'sem-ant', 'sem-prox', 'sem-atual'].forEach((id) => { $(id).disabled = estado.todas; });
  if (estado.todas) {
    $('intervalo').textContent = 'Exibindo todo o planejamento';
  } else {
    const { inicio, fim } = semanaParaIntervalo(estado.semana);
    $('intervalo').textContent = `${fmtDataLonga(inicio)} a ${fmtDataLonga(fim)}`;
  }
  const p = periodo();
  $('exportar').href = `/api/exportacao/excel${api.qs(p)}`;
  localStorage.setItem('mineplan.periodo', JSON.stringify({ semana: estado.semana, todas: estado.todas }));
}

function moverSemana(n) {
  const { inicio } = semanaParaIntervalo(estado.semana);
  estado.semana = dataParaSemana(addDias(inicio, 7 * n));
  atualizar();
}

$('sem-ant').onclick = () => moverSemana(-1);
$('sem-prox').onclick = () => moverSemana(1);
$('sem-atual').onclick = () => { estado.semana = dataParaSemana(new Date()); atualizar(); };
$('semana').onchange = (e) => { if (e.target.value) { estado.semana = e.target.value; atualizar(); } };
$('todas').onchange = (e) => { estado.todas = e.target.checked; atualizar(); };
$('data-ref').onchange = (e) => {
  estado.dataRef = e.target.value || hojeISO();
  if (estado.dataRef !== hojeISO()) toast(`Situações calculadas para ${fmtDataLonga(estado.dataRef)}.`, 'info');
  atualizar();
};

window.addEventListener('hashchange', atualizar);
atualizar();
