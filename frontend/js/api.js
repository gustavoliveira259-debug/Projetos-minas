async function req(metodo, url, corpo) {
  const opts = { method: metodo, headers: {} };
  if (corpo instanceof FormData) opts.body = corpo;
  else if (corpo !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(corpo);
  }
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const j = await r.json();
      if (typeof j.detail === 'string') msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d) => d.msg.replace(/^Value error, /, '')).join(' ');
    } catch { /* corpo não-JSON */ }
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}

const qs = (p) => {
  const s = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== ''));
  return s.toString() ? `?${s}` : '';
};

export const api = {
  qs,
  atividades: (p = {}) => req('GET', `/api/atividades${qs(p)}`),
  filtros: () => req('GET', '/api/atividades/filtros'),
  criar: (d) => req('POST', '/api/atividades', d),
  atualizar: (id, d) => req('PATCH', `/api/atividades/${id}`, d),
  excluir: (id) => req('DELETE', `/api/atividades/${id}`),
  reabrir: (id) => req('POST', `/api/atividades/${id}/reabrir`),
  apontamentos: (id) => req('GET', `/api/atividades/${id}/apontamentos`),
  apontar: (id, d) => req('POST', `/api/atividades/${id}/apontamentos`, d),
  excluirApontamento: (id) => req('DELETE', `/api/apontamentos/${id}`),
  indicadores: (p = {}) => req('GET', `/api/indicadores${qs(p)}`),
  equipamentos: () => req('GET', '/api/equipamentos'),
  painelFrota: (p = {}) => req('GET', `/api/equipamentos/painel${qs(p)}`),
  criarEquipamento: (d) => req('POST', '/api/equipamentos', d),
  atualizarEquipamento: (id, d) => req('PATCH', `/api/equipamentos/${id}`, d),
  excluirEquipamento: (id) => req('DELETE', `/api/equipamentos/${id}`),
  sincronizarEquipamentos: () => req('POST', '/api/equipamentos/sincronizar'),
  paradas: (id) => req('GET', `/api/equipamentos/${id}/paradas`),
  criarParada: (id, d) => req('POST', `/api/equipamentos/${id}/paradas`, d),
  atualizarParada: (id, d) => req('PATCH', `/api/paradas/${id}`, d),
  excluirParada: (id) => req('DELETE', `/api/paradas/${id}`),
  horas: (id) => req('GET', `/api/equipamentos/${id}/horas`),
  registrarHoras: (id, d) => req('POST', `/api/equipamentos/${id}/horas`, d),
  excluirHoras: (id) => req('DELETE', `/api/horas/${id}`),
  importar: (arquivo, confirmar, modo) => {
    const fd = new FormData();
    fd.append('arquivo', arquivo);
    return req('POST', `/api/importacao${qs({ confirmar, modo })}`, fd);
  },
};
