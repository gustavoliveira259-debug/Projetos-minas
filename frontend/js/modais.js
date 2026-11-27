import { api } from './api.js';
import { addDias, badge, difDias, esc, fmtData, fmtDataLonga, fmtNum, fmtPct, hojeISO, parseISO, toISO, toast } from './util.js';

const modal = () => document.getElementById('modal');

export function abrir(html) {
  const m = modal();
  m.innerHTML = html;
  m.showModal();
  m.querySelectorAll('[data-fechar]').forEach((b) => { b.onclick = () => m.close(); });
  m.querySelector('input:not([type=hidden]), select, textarea')?.focus();
  return m;
}

let filtrosCache = null;
async function sugestoes() {
  filtrosCache ??= await api.filtros().catch(() => ({}));
  return filtrosCache;
}
export const limparSugestoes = () => { filtrosCache = null; };

const lista = (id, valores = []) =>
  `<datalist id="${id}">${valores.map((v) => `<option value="${esc(v)}">`).join('')}</datalist>`;

const rotuloAtiv = (x) => `${x.codigo ? `${x.codigo} — ` : ''}${x.descricao}`;

/** Avisa quais dependentes foram adiadas pela alteração (resposta do PATCH). */
export function avisarEmpurradas(resp) {
  const e = resp?.empurradas || [];
  if (!e.length) return;
  const lista = e.slice(0, 3).map((x) => `${x.codigo || x.descricao} → ${fmtData(x.inicio_planejado)}`).join(', ');
  toast(`${e.length} dependente${e.length > 1 ? 's empurradas' : ' empurrada'}: ${lista}${e.length > 3 ? '…' : ''}`, 'info');
}

/** Ids das atividades que dependem (direta ou indiretamente) de `id`: não podem virar predecessoras dela. */
function descendentes(id, todas) {
  const porId = new Map(todas.map((x) => [x.id, x]));
  const saida = new Set();
  const pilha = [id];
  while (pilha.length) {
    for (const s of porId.get(pilha.pop())?.sucessoras || []) {
      if (!saida.has(s.id)) { saida.add(s.id); pilha.push(s.id); }
    }
  }
  return saida;
}

/** Formulário de cadastro / edição. `atividade` nulo = nova. `padrao` preenche datas iniciais. */
export async function formAtividade(atividade, aoSalvar, padrao = {}) {
  const a = atividade || { unidade: 't', qtd_planejada: 0, ...padrao };
  const [f, todas] = await Promise.all([sugestoes(), api.atividades().catch(() => [])]);
  const selecionadas = new Set((a.predecessoras || []).map((p) => p.id));
  const bloqueadas = atividade ? descendentes(atividade.id, todas) : new Set();
  const candidatas = todas
    .filter((x) => x.id !== a.id && !bloqueadas.has(x.id))
    .sort((x, y) => (selecionadas.has(y.id) - selecionadas.has(x.id)) || x.inicio_planejado.localeCompare(y.inicio_planejado));
  const v = (k) => esc(a[k] ?? '');
  const m = abrir(`
    <form method="dialog" class="form" id="f-ativ">
      <header><h2>${atividade ? 'Editar atividade' : 'Nova atividade'}</h2>
        <button type="button" class="btn icone" data-fechar aria-label="Fechar">×</button></header>
      <div class="grade">
        <label class="c2">Descrição*<input name="descricao" required maxlength="255" value="${v('descricao')}"></label>
        <label>Código<input name="codigo" maxlength="50" value="${v('codigo')}" placeholder="ex.: CG-101"></label>
        <label>Tipo<input name="tipo" list="dl-tipos" value="${v('tipo')}" placeholder="Perfuração, Desmonte…"></label>
        <label>Frente de lavra<input name="frente" list="dl-frentes" value="${v('frente')}"></label>
        <label>Equipamento<input name="equipamento" list="dl-equip" value="${v('equipamento')}"></label>
        <label>Responsável<input name="responsavel" list="dl-resp" value="${v('responsavel')}"></label>
        <label>Quantidade planejada<input name="qtd_planejada" type="number" min="0" step="any" value="${v('qtd_planejada')}"></label>
        <label>Unidade<input name="unidade" list="dl-un" value="${v('unidade')}" required></label>
        <label>Início planejado*<input name="inicio_planejado" type="date" required value="${v('inicio_planejado')}"></label>
        <label>Fim planejado*<input name="fim_planejado" type="date" required value="${v('fim_planejado')}"></label>
        <label>Início real<input name="inicio_real" type="date" value="${v('inicio_real')}"></label>
        <label>Fim real (conclusão)<input name="fim_real" type="date" value="${v('fim_real')}"></label>
        <label title="Use quando a atividade não tem quantidade (ex.: infraestrutura)">Progresso manual (%)
          <input name="progresso_manual" type="number" min="0" max="100" step="1" value="${v('progresso_manual')}"></label>
        <label class="c3">Observações<textarea name="observacoes" rows="2">${v('observacoes')}</textarea></label>
        <fieldset class="c3 deps">
          <legend>Depende de <span class="mudo">— só pode começar quando estas terminarem; se forem adiadas, esta é empurrada junto</span></legend>
          ${candidatas.length ? `<input type="search" class="deps-busca" placeholder="Filtrar por código, descrição ou frente…" aria-label="Filtrar atividades">
          <ul class="deps-lista">${candidatas.map((x) => `<li data-busca="${esc(`${x.codigo || ''} ${x.descricao} ${x.frente || ''}`.toLowerCase())}">
            <label class="chk"><input type="checkbox" name="pred" value="${x.id}" data-fim="${x.fim_planejado}" ${selecionadas.has(x.id) ? 'checked' : ''}>
              <span>${esc(rotuloAtiv(x))}</span><small class="mudo">${esc(x.frente || '')} · ${fmtData(x.inicio_planejado)}–${fmtData(x.fim_planejado)}</small></label></li>`).join('')}
          </ul>
          <p class="mudo deps-resumo" aria-live="polite"></p>` : '<p class="mudo">Nenhuma outra atividade cadastrada.</p>'}
        </fieldset>
      </div>
      ${lista('dl-tipos', f.tipos)}${lista('dl-frentes', f.frentes)}${lista('dl-equip', f.equipamentos)}
      ${lista('dl-resp', f.responsaveis)}${lista('dl-un', [...new Set(['t', 'm³', 'm', 'un', ...(f.unidades || [])])])}
      <p class="erro-form" hidden></p>
      <footer>
        ${atividade ? '<button type="button" class="btn perigo" id="excluir">Excluir</button>' : ''}
        <span class="esp"></span>
        <button type="button" class="btn texto" data-fechar>Cancelar</button>
        <button type="submit" class="btn primario">Salvar</button>
      </footer>
    </form>`);

  const form = m.querySelector('form');
  const erro = m.querySelector('.erro-form');
  form.inicio_planejado.addEventListener('change', () => {
    if (!form.fim_planejado.value || form.fim_planejado.value < form.inicio_planejado.value) {
      form.fim_planejado.value = form.inicio_planejado.value;
    }
  });

  // Dependências: filtro, resumo e ajuste automático do início para depois da predecessora.
  const caixas = [...form.querySelectorAll('input[name=pred]')];
  const resumo = form.querySelector('.deps-resumo');
  const pintarResumo = (aviso = '') => {
    if (!resumo) return;
    const marcadas = caixas.filter((c) => c.checked);
    const limite = marcadas.map((c) => c.dataset.fim).sort().pop();
    resumo.textContent = marcadas.length
      ? `${marcadas.length} selecionada${marcadas.length > 1 ? 's' : ''} · pode começar a partir de ${fmtDataLonga(limite)}.${aviso}`
      : 'Nenhuma dependência.';
  };
  caixas.forEach((c) => c.addEventListener('change', () => {
    let aviso = '';
    const ini = form.inicio_planejado.value;
    if (c.checked && ini && ini < c.dataset.fim) {
      const dur = form.fim_planejado.value ? difDias(parseISO(ini), parseISO(form.fim_planejado.value)) : 0;
      form.inicio_planejado.value = c.dataset.fim;
      form.fim_planejado.value = toISO(addDias(parseISO(c.dataset.fim), Math.max(dur, 0)));
      aviso = ' Datas ajustadas para depois da predecessora.';
    }
    pintarResumo(aviso);
  }));
  form.querySelector('.deps-busca')?.addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    form.querySelectorAll('.deps-lista li').forEach((li) => { li.hidden = !!q && !li.dataset.busca.includes(q); });
  });
  pintarResumo();

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const dados = { predecessoras: caixas.filter((c) => c.checked).map((c) => Number(c.value)) };
    for (const [k, val] of new FormData(form)) {
      if (k === 'pred') continue;
      const t = String(val).trim();
      if (['qtd_planejada', 'progresso_manual'].includes(k)) dados[k] = t === '' ? (k === 'qtd_planejada' ? 0 : null) : Number(t);
      else dados[k] = t === '' ? null : t;
    }
    try {
      const resp = atividade ? await api.atualizar(atividade.id, dados) : await api.criar(dados);
      limparSugestoes();
      m.close();
      toast(atividade ? 'Atividade atualizada.' : 'Atividade criada.');
      avisarEmpurradas(resp);
      aoSalvar?.();
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
    }
  };

  m.querySelector('#excluir')?.addEventListener('click', async () => {
    if (!confirm(`Excluir "${atividade.descricao}" e todos os seus apontamentos?`)) return;
    try {
      await api.excluir(atividade.id);
      m.close();
      toast('Atividade excluída.');
      aoSalvar?.();
    } catch (e) { toast(e.message, 'erro'); }
  });
}

/** Registro de andamento: produção do dia + histórico. */
export async function modalApontamento(atividade, aoSalvar) {
  const historico = await api.apontamentos(atividade.id);
  const s = atividade.situacao;
  const semQtd = !atividade.qtd_planejada;
  const m = abrir(`
    <form method="dialog" class="form" id="f-apont">
      <header><h2>Atualizar andamento</h2>
        <button type="button" class="btn icone" data-fechar aria-label="Fechar">×</button></header>
      <div class="resumo-ativ">
        <div><strong>${esc(atividade.codigo || '')} ${esc(atividade.descricao)}</strong>
          <span class="mudo">${esc(atividade.frente || '')} · ${fmtDataLonga(atividade.inicio_planejado)} a ${fmtDataLonga(atividade.fim_planejado)}${atividade.responsavel ? ` · Responsável: ${esc(atividade.responsavel)}` : ''}</span></div>
        ${badge(s.status)}
      </div>
      <dl class="numeros">
        <div><dt>Planejado</dt><dd>${fmtNum(atividade.qtd_planejada)} ${esc(atividade.unidade)}</dd></div>
        <div><dt>Realizado</dt><dd>${fmtNum(s.qtd_realizada)} ${esc(atividade.unidade)}</dd></div>
        <div><dt>Progresso</dt><dd>${fmtPct(s.progresso_real)} <small class="mudo">esperado ${fmtPct(s.progresso_esperado)}</small></dd></div>
        <div><dt>Saldo</dt><dd>${fmtNum(s.saldo)} ${esc(atividade.unidade)}</dd></div>
      </dl>
      <div class="grade">
        <label>Data<input name="data" type="date" required value="${hojeISO()}"></label>
        <label>${semQtd ? 'Quantidade (opcional)' : `Quantidade realizada (${esc(atividade.unidade)})`}
          <input name="quantidade" type="number" min="0" step="any" ${semQtd ? '' : 'required'} placeholder="0"></label>
        ${semQtd ? `<label>Progresso manual (%)<input name="progresso_manual" type="number" min="0" max="100" value="${atividade.progresso_manual ?? ''}"></label>` : '<span></span>'}
        <label class="c3">Observação<input name="observacao" maxlength="255" placeholder="Turno, ocorrência, motivo do desvio…"></label>
        <label class="chk c3"><input type="checkbox" name="concluir" ${atividade.fim_real ? 'disabled' : ''}> Marcar atividade como concluída nesta data</label>
      </div>
      <p class="erro-form" hidden></p>
      <footer>
        ${atividade.fim_real ? '<button type="button" class="btn texto" id="reabrir">Reabrir atividade</button>' : ''}
        <span class="esp"></span>
        <button type="button" class="btn texto" data-fechar>Fechar</button>
        <button type="submit" class="btn primario">Registrar</button>
      </footer>
      <h3>Histórico de apontamentos</h3>
      ${historico.length ? `<table class="tabela compacta"><thead><tr><th>Data</th><th class="num">Quantidade</th><th>Observação</th><th></th></tr></thead><tbody>
        ${historico.slice().reverse().map((p) => `<tr><td>${fmtDataLonga(p.data)}</td><td class="num">${fmtNum(p.quantidade)}</td>
          <td>${esc(p.observacao || '')}</td><td><button type="button" class="btn icone mini" data-del="${p.id}" title="Excluir apontamento" aria-label="Excluir apontamento">×</button></td></tr>`).join('')}
      </tbody></table>` : '<p class="mudo">Nenhum apontamento registrado.</p>'}
    </form>`);

  const form = m.querySelector('form');
  const erro = m.querySelector('.erro-form');
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      if (semQtd && form.progresso_manual && form.progresso_manual.value !== '') {
        await api.atualizar(atividade.id, { progresso_manual: Number(form.progresso_manual.value) });
      }
      await api.apontar(atividade.id, {
        data: form.data.value,
        quantidade: Number(form.quantidade.value || 0),
        observacao: form.observacao.value.trim() || null,
        concluir: form.concluir.checked,
      });
      m.close();
      toast('Andamento registrado.');
      aoSalvar?.();
    } catch (e) {
      erro.textContent = e.message;
      erro.hidden = false;
    }
  };
  m.querySelector('#reabrir')?.addEventListener('click', async () => {
    await api.reabrir(atividade.id);
    m.close();
    toast('Atividade reaberta.');
    aoSalvar?.();
  });
  m.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Excluir este apontamento?')) return;
    await api.excluirApontamento(b.dataset.del);
    m.close();
    aoSalvar?.();
    toast('Apontamento excluído.');
  }));
}
