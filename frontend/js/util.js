export const STATUS = {
  nao_iniciada: { rotulo: 'Não iniciada', icone: '○' },
  no_prazo: { rotulo: 'No prazo', icone: '●' },
  adiantada: { rotulo: 'Adiantada', icone: '▲' },
  atrasada: { rotulo: 'Atrasada', icone: '!' },
  concluida: { rotulo: 'Concluída', icone: '✓' },
};

const nf = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

export const fmtNum = (v, casas) => v == null || isNaN(v) ? '—'
  : (casas === 0 || Math.abs(v) >= 1000 ? nf0 : nf).format(v);
export const fmtPct = (v) => v == null ? '—' : `${nf.format(v * 100)}%`;
export const fmtPP = (v) => v == null ? '—' : `${v > 0 ? '+' : ''}${nf.format(v * 100)} p.p.`;

export function parseISO(s) {
  if (!s) return null;
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}
export function toISO(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
export const addDias = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
export const difDias = (a, b) => Math.round((b - a) / 86400000);
export const fmtData = (s) => {
  const d = typeof s === 'string' ? parseISO(s) : s;
  return d ? d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : '—';
};
export const fmtDataLonga = (s) => {
  const d = typeof s === 'string' ? parseISO(s) : s;
  return d ? d.toLocaleDateString('pt-BR') : '—';
};
export const hojeISO = () => toISO(new Date());

/** "2026-W48" -> {inicio: Date(seg), fim: Date(dom)} */
export function semanaParaIntervalo(valor) {
  const [ano, w] = valor.split('-W').map(Number);
  const jan4 = new Date(ano, 0, 4);
  const seg1 = addDias(jan4, -((jan4.getDay() + 6) % 7));
  const inicio = addDias(seg1, (w - 1) * 7);
  return { inicio, fim: addDias(inicio, 6) };
}
export function dataParaSemana(d) {
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  t.setDate(t.getDate() + 3 - ((t.getDay() + 6) % 7));
  const ano = t.getFullYear();
  const jan4 = new Date(ano, 0, 4);
  const w = 1 + Math.round(((t - jan4) / 86400000 - 3 + ((jan4.getDay() + 6) % 7)) / 7);
  return `${ano}-W${String(w).padStart(2, '0')}`;
}

export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function badge(status) {
  const s = STATUS[status] || { rotulo: status, icone: '' };
  return `<span class="badge st-${status}"><i aria-hidden="true">${s.icone}</i>${s.rotulo}</span>`;
}

export function toast(msg, tipo = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${tipo}`;
  el.textContent = msg;
  document.getElementById('toasts').append(el);
  setTimeout(() => el.classList.add('sai'), 3500);
  setTimeout(() => el.remove(), 4000);
}

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

const tip = () => document.getElementById('tooltip');
export function mostrarTooltip(html, x, y) {
  const el = tip();
  el.innerHTML = html;
  el.hidden = false;
  const r = el.getBoundingClientRect();
  const left = Math.min(x + 14, window.innerWidth - r.width - 8);
  const top = y + 16 + r.height > window.innerHeight ? y - r.height - 10 : y + 16;
  el.style.left = `${Math.max(8, left)}px`;
  el.style.top = `${Math.max(8, top)}px`;
}
export const esconderTooltip = () => { tip().hidden = true; };

/** "2026-11-24T12:00:00" -> Date local */
export const parseDataHora = (s) => (s ? new Date(s.length === 10 ? `${s}T00:00` : s) : null);
export const fmtDataHora = (s) => {
  const d = typeof s === 'string' ? parseDataHora(s) : s;
  return d ? `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })} ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}` : '—';
};
/** Date -> valor de <input type="datetime-local"> */
export const paraDataHoraLocal = (d) => `${toISO(d)}T${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
export const fmtHoras = (h) => (h == null ? '—' : `${fmtNum(h)} h`);
