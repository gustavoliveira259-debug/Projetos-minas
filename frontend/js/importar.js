import { api } from './api.js';
import { limparSugestoes } from './modais.js';
import { esc, fmtData, fmtNum, toast } from './util.js';

const ROTULOS_CAMPO = {
  codigo: 'Código', descricao: 'Descrição', tipo: 'Tipo', frente: 'Frente', equipamento: 'Equipamento',
  responsavel: 'Responsável', unidade: 'Unidade', qtd_planejada: 'Qtd planejada', qtd_realizada: 'Qtd realizada',
  inicio_planejado: 'Início planejado', fim_planejado: 'Fim planejado', duracao: 'Duração (dias)',
  inicio_real: 'Início real', fim_real: 'Fim real', observacoes: 'Observações',
};

let arquivo = null;

export function renderImportar(main) {
  arquivo = null;
  main.innerHTML = `
    <div class="cabecalho-pagina">
      <div><h1>Importar planejamento</h1>
        <p class="mudo">Envie a planilha semanal (.xlsx ou .csv). Você verá uma prévia antes de gravar.</p></div>
      <a class="btn" href="/api/importacao/modelo" download>⇩ Baixar modelo de planilha</a>
    </div>
    <section class="cartao">
      <label class="soltar" id="soltar">
        <input type="file" id="arquivo" accept=".xlsx,.xlsm,.csv" hidden>
        <strong>Arraste a planilha aqui</strong><span class="mudo">ou clique para escolher o arquivo</span>
        <span id="nome-arquivo" class="nome-arquivo"></span>
      </label>
      <div class="opcoes-importacao">
        <fieldset>
          <legend>Modo de importação</legend>
          <label class="chk"><input type="radio" name="modo" value="mesclar" checked> <span><b>Mesclar</b> — atualiza atividades com o mesmo código e adiciona as novas</span></label>
          <label class="chk"><input type="radio" name="modo" value="substituir"> <span><b>Substituir tudo</b> — apaga todas as atividades e apontamentos antes de importar</span></label>
        </fieldset>
      </div>
    </section>
    <div id="previa"></div>`;

  const input = main.querySelector('#arquivo');
  const zona = main.querySelector('#soltar');
  const escolher = (f) => {
    if (!f) return;
    arquivo = f;
    main.querySelector('#nome-arquivo').textContent = f.name;
    previsualizar(main);
  };
  input.onchange = () => escolher(input.files[0]);
  zona.addEventListener('dragover', (e) => { e.preventDefault(); zona.classList.add('sobre'); });
  zona.addEventListener('dragleave', () => zona.classList.remove('sobre'));
  zona.addEventListener('drop', (e) => { e.preventDefault(); zona.classList.remove('sobre'); escolher(e.dataTransfer.files[0]); });
  main.querySelectorAll('input[name=modo]').forEach((r) => r.addEventListener('change', () => arquivo && previsualizar(main)));
}

const modoAtual = (main) => main.querySelector('input[name=modo]:checked').value;

async function previsualizar(main) {
  const alvo = main.querySelector('#previa');
  alvo.innerHTML = '<p class="mudo carregando">Lendo planilha…</p>';
  let r;
  try {
    r = await api.importar(arquivo, false, modoAtual(main));
  } catch (e) {
    alvo.innerHTML = `<div class="cartao erro"><strong>Não foi possível importar.</strong><p>${esc(e.message)}</p></div>`;
    return;
  }
  const colunas = Object.entries(r.colunas_reconhecidas);
  const campos = ['codigo', 'descricao', 'frente', 'tipo', 'unidade', 'qtd_planejada', 'inicio_planejado', 'fim_planejado'];
  alvo.innerHTML = `
    <section class="cartao">
      <h2>Prévia da importação</h2>
      <p class="mudo">${esc(r.arquivo)}${r.aba ? ` · aba “${esc(r.aba)}”` : ''} · cabeçalho na linha ${r.linha_cabecalho}</p>
      <div class="resumo-importacao">
        <div><b>${r.criar}</b><span>novas</span></div>
        <div><b>${r.atualizar}</b><span>a atualizar</span></div>
        <div class="${r.com_erro ? 'txt-atrasada' : ''}"><b>${r.com_erro}</b><span>com erro (ignoradas)</span></div>
      </div>
      <details><summary>Colunas reconhecidas (${colunas.length})${r.colunas_ignoradas.length ? ` · ${r.colunas_ignoradas.length} ignoradas` : ''}</summary>
        <ul class="mapa-colunas">${colunas.map(([orig, campo]) => `<li><span>${esc(orig)}</span> → <b>${ROTULOS_CAMPO[campo] || campo}</b></li>`).join('')}
        ${r.colunas_ignoradas.map((c) => `<li class="mudo"><span>${esc(c)}</span> → ignorada</li>`).join('')}</ul>
      </details>
      <div class="tabela-rolagem alta"><table class="tabela compacta">
        <thead><tr><th>Linha</th><th>Ação</th>${campos.map((c) => `<th>${ROTULOS_CAMPO[c]}</th>`).join('')}<th>Realizado</th><th>Problemas</th></tr></thead>
        <tbody>${r.linhas.map((l) => `<tr class="${l.acao === 'erro' ? 'linha-erro' : ''}">
          <td>${l.linha}</td><td><span class="acao-${l.acao}">${{ criar: 'Nova', atualizar: 'Atualizar', erro: 'Erro' }[l.acao]}</span></td>
          ${campos.map((c) => `<td>${fmtCampo(c, l.dados[c])}</td>`).join('')}
          <td>${l.qtd_realizada == null ? '' : fmtNum(l.qtd_realizada)}</td>
          <td class="txt-atrasada">${l.erros.map(esc).join('; ')}</td></tr>`).join('')}</tbody>
      </table></div>
      <footer class="acoes-importacao">
        <span class="mudo">${r.modo === 'substituir' ? '⚠ Todas as atividades atuais serão apagadas.' : ''}</span>
        <button class="btn primario" id="confirmar" ${r.criar + r.atualizar ? '' : 'disabled'}>Importar ${r.criar + r.atualizar} atividade${r.criar + r.atualizar === 1 ? '' : 's'}</button>
      </footer>
    </section>`;

  alvo.querySelector('#confirmar').onclick = async (ev) => {
    if (r.modo === 'substituir' && !confirm('Isso apagará TODAS as atividades e apontamentos atuais. Continuar?')) return;
    ev.target.disabled = true;
    try {
      const fim = await api.importar(arquivo, true, r.modo);
      limparSugestoes();
      toast(`${fim.criar} criadas, ${fim.atualizar} atualizadas${fim.com_erro ? `, ${fim.com_erro} ignoradas` : ''}.`);
      location.hash = '#/gantt';
    } catch (e) {
      toast(e.message, 'erro');
      ev.target.disabled = false;
    }
  };
}

function fmtCampo(c, v) {
  if (v == null || v === '') return '';
  if (c.endsWith('planejado') || c.endsWith('_real')) return fmtData(v);
  if (c === 'qtd_planejada') return fmtNum(v);
  return esc(v);
}
