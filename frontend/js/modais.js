import { api } from './api.js';
import { badge, esc, fmtDataLonga, fmtNum, fmtPct, hojeISO, toast } from './util.js';

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

/** Formulário de cadastro / edição. `atividade` nulo = nova. `padrao` preenche datas iniciais. */
export async function formAtividade(atividade, aoSalvar, padrao = {}) {
  const a = atividade || { unidade: 't', qtd_planejada: 0, ...padrao };
  const f = await sugestoes();
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

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const dados = {};
    for (const [k, val] of new FormData(form)) {
      const t = String(val).trim();
      if (['qtd_planejada', 'progresso_manual'].includes(k)) dados[k] = t === '' ? (k === 'qtd_planejada' ? 0 : null) : Number(t);
      else dados[k] = t === '' ? null : t;
    }
    try {
      if (atividade) await api.atualizar(atividade.id, dados);
      else await api.criar(dados);
      limparSugestoes();
      m.close();
      toast(atividade ? 'Atividade atualizada.' : 'Atividade criada.');
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
          <span class="mudo">${esc(atividade.frente || '')} · ${fmtDataLonga(atividade.inicio_planejado)} a ${fmtDataLonga(atividade.fim_planejado)}</span></div>
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
