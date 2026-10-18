const COLORES_CSS = {
  'negro': '#111111', 'blanco': '#ffffff', 'gris': '#8a8a8a',
  'gris claro': '#d0d0d0', 'gris oscuro': '#4a4a4a', 'plomo': '#6e6e73',
  'rojo': '#c62828', 'vino': '#6d1b2b', 'guinda': '#6d1b2b', 'rosa': '#f4a6c0',
  'rosa palo': '#f0c9c9', 'fucsia': '#d81b87', 'naranja': '#ef7d22',
  'amarillo': '#f2cc2f', 'mostaza': '#c9a227', 'beige': '#d9c6a5',
  'crema': '#f3ead3', 'cafe': '#6b4428', 'marron': '#6b4428', 'camel': '#b98550',
  'khaki': '#b8a76a', 'verde': '#2e7d4f', 'verde oliva': '#6b7036',
  'verde militar': '#4b5320', 'verde menta': '#a8dcc0', 'verde botella': '#0b3d2e',
  'azul': '#1f5fbf', 'azul marino': '#14213d', 'azul cielo': '#8ec5ee',
  'azul rey': '#1c3faa', 'celeste': '#9fd3f2', 'turquesa': '#20b2aa',
  'morado': '#6a3d9a', 'lila': '#c4a7e0', 'lavanda': '#d8c8ee',
  'dorado': '#d4af37', 'plateado': '#c0c0c0', 'mezclilla': '#4a6fa5',
  'multicolor': 'linear-gradient(135deg,#e53935,#fdd835,#43a047,#1e88e5,#8e24aa)',
};

const state = { config: null, prendas: [], filters: {}, editId: null };
const $ = (sel) => document.querySelector(sel);
const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (!dialog.open) dialog.showModal();
}

function closeDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog.open) dialog.close();
}

document.addEventListener('click', (event) => {
  const close = event.target.closest('[data-close]');
  if (close) closeDialog(close.dataset.close);
});

async function loadConfig() {
  const response = await fetch('/api/config');
  state.config = await response.json();
  await migrarHexLocales();
  renderDynamicFilters();
  renderFormFields('#garment-fields', state.config.campos, 'garment');
  renderFormFields('#batch-fields', state.config.campos, 'batch');
  initFiltersFromUrl();
  await loadPrendas();
}

async function addSeasonOption() {
  const input = $('#season-option-input');
  const option = input.value.trim();
  if (!option) return;
  const body = new FormData();
  body.append('campo', 'temporada');
  body.append('opcion', option);
  const response = await fetch('/field/option', { method: 'POST', body });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    alert(data.error || 'No se pudo agregar la opción.');
    return;
  }
  input.value = '';
  await loadConfig();
  alert(`Se agregó "${option}" a temporada.`);
}

async function loadPrendas() {
  const params = new URLSearchParams(state.filters);
  const response = await fetch('/api/prendas?' + params.toString());
  const data = await response.json();
  state.prendas = data.prendas || [];
  $('#count-pill').textContent = `${state.prendas.length} prendas`;
  $('#count-pill-top').textContent = `${state.prendas.length} prendas`;
  const grid = $('#card-grid');
  grid.innerHTML = '';
  if (!state.prendas.length) {
    $('#empty-state').classList.remove('hidden');
    return;
  }
  $('#empty-state').classList.add('hidden');
  for (const prenda of state.prendas) grid.appendChild(renderCard(prenda));
}
function renderDynamicFilters() {
  const container = $('#dynamic-filters');
  container.innerHTML = '';
  for (const campo of state.config.campos) {
    const wrap = document.createElement('div');
    const label = document.createElement('label');
    label.setAttribute('for', `filter-${campo.nombre}`);
    label.textContent = campo.etiqueta;
    wrap.appendChild(label);

    let control;
    if (campo.tipo === 'lista' && campo.nombre === 'color') {
      const picker = buildColorPicker(campo, `filter-${campo.nombre}`, campo.nombre, true);
      control = picker.campoInput;               // input hidden con id filter-color
      wrap.appendChild(picker);
    } else {
      control = document.createElement(campo.tipo === 'lista' ? 'select' : 'input');
      control.id = `filter-${campo.nombre}`;
      control.name = campo.nombre;
      if (campo.tipo === 'lista') {
        control.innerHTML = `<option value="">Todos</option>${(campo.opciones || []).map(op => `<option value="${escapeHtml(op)}">${escapeHtml(op)}</option>`).join('')}`;
      } else {
        control.type = 'text';
        control.placeholder = campo.etiqueta;
      }
      wrap.appendChild(control);
    }
    container.appendChild(wrap);
    control.addEventListener('change', applyFilters);
    control.addEventListener('input', applyFilters);
  }
}

function applyFilters(event) {
    if (event) event.preventDefault();
    const filters = {};
    const params = new URLSearchParams();

    const q = $('#q').value.trim();
    if (q) {
        filters.q = q;
        params.append('q', q);
    }

    for (const campo of state.config.campos) {
        const value = $(`#filter-${campo.nombre}`).value.trim();
        if (value) {
        filters[campo.nombre] = value;
        params.append(campo.nombre, value);
        }
    }

    state.filters = filters;

    const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
    history.pushState(null, '', newUrl);

    loadPrendas();
}

//
const normalizarTexto = (t) => String(t ?? '')
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

function cssDeColor(nombre) {
  const n = normalizarTexto(nombre);
  const propio = leerHexGuardados()[n];
  if (propio) return propio;
  if (COLORES_CSS[n]) return COLORES_CSS[n];
  const primera = n.split(/\s+/)[0];
  return COLORES_CSS[primera] || null;
}


function buildColorPicker(campo, fieldId, name, compacto = false, permitirAgregar = false) {  const root = document.createElement('div');
  root.className = 'color-picker' + (compacto ? ' compacto' : '');

  const hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.id = fieldId;
  hidden.name = name;

  const search = document.createElement('input');
  search.type = 'search';
  search.placeholder = 'Buscar color...';
  search.autocomplete = 'off';

  const status = document.createElement('div');
  status.className = 'color-status hint';

  const grid = document.createElement('div');
  grid.className = 'color-grid';

  const empty = document.createElement('div');
  empty.className = 'color-empty hint hidden';
  empty.textContent = 'Ningún color coincide.';

  const celdas = [];
  for (const op of (campo.opciones || [])) {
    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'color-cell';
    cell.dataset.valor = op;
    cell.dataset.texto = normalizarTexto(op);
    cell.title = op;
    cell.setAttribute('aria-label', op);
    const swatch = document.createElement('span');
    swatch.className = 'color-swatch';
    const css = cssDeColor(op);
    if (css) swatch.style.background = css; else swatch.classList.add('sin-muestra');
    cell.appendChild(swatch);
    if (!compacto) {
      const text = document.createElement('span');
      text.className = 'color-name';
      text.textContent = op;
      cell.appendChild(text);
    }
    cell.addEventListener('click', () => {
      hidden.value = hidden.value === op ? '' : op;   // clic otra vez = quitar
      refresh();
      hidden.dispatchEvent(new Event('change', { bubbles: true })); // para el filtro
    });
    grid.appendChild(cell);
    celdas.push(cell);
  }

  function filtrar() {
    const q = normalizarTexto(search.value);
    let visibles = 0;
    for (const c of celdas) {
      const ok = !q || c.dataset.texto.includes(q);
      c.classList.toggle('hidden', !ok);
      if (ok) visibles++;
    }
    empty.classList.toggle('hidden', visibles > 0);
  }

  function refresh() {
    for (const c of celdas) c.classList.toggle('selected', c.dataset.valor === hidden.value);
    status.textContent = hidden.value
      ? `Seleccionado: ${hidden.value}`
      : (compacto ? 'Todos los colores' : 'Sin color seleccionado');
    filtrar();
  }

  search.addEventListener('input', filtrar);
  search.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const visibles = celdas.filter(c => !c.classList.contains('hidden'));
    if (visibles.length === 1) visibles[0].click();
  });

  root.refresh = refresh;
  root.campoInput = hidden;
  root._cfg = { fieldId, name, compacto, permitirAgregar };

  const extras = [];
  if (permitirAgregar) {
    const btnAgregar = document.createElement('button');
    btnAgregar.type = 'button';
    btnAgregar.className = 'btn secondary color-agregar';
    btnAgregar.textContent = '+ Agregar color';
    btnAgregar.addEventListener('click', () => {
      abrirDialogoColor((nom, hex) => agregarColorNuevo(nom, hex, fieldId));
    });
    extras.push(btnAgregar);
  }
  root.append(hidden, search, status, grid, empty, ...extras);
  refresh();
  return root;
}

function refreshColorPickers() {
  document.querySelectorAll('.color-picker').forEach(p => p.refresh());
}

// ---------- Colores propios: hex en localStorage + diálogo con paleta hexagonal ----------
const HEX_KEY = 'ropero_colores_hex';

function hexDeServidor(nombre) {
  const campo = state.config?.campos.find(c => c.nombre === 'color');
  const n = normalizarTexto(nombre);
  for (const [op, hex] of Object.entries(campo?.colores || {})) {
    if (normalizarTexto(op) === n) return hex;
  }
  return null;
}

function cssDeColor(nombre) {
  const n = normalizarTexto(nombre);
  return hexDeServidor(nombre) || COLORES_CSS[n] || COLORES_CSS[n.split(/\s+/)[0]] || null;
}

function hslAHex(h, s, l) {
  s /= 100; l /= 100;
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const aHex = (x) => Math.round(x * 255).toString(16).padStart(2, '0');
  return `#${aHex(f(0))}${aHex(f(8))}${aHex(f(4))}`;
}

// Acepta "#abc", "abc", "#aabbcc", "aabbcc". Devuelve "#aabbcc" o null.
function normalizarHex(valor) {
  let v = String(valor ?? '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(v)) v = v.split('').map(c => c + c).join('');
  return /^[0-9a-f]{6}$/i.test(v) ? '#' + v.toLowerCase() : null;
}

function reemplazarColorPickers(campoColor) {
  document.querySelectorAll('.color-picker').forEach(viejo => {
    const cfg = viejo._cfg;
    const nuevo = buildColorPicker(campoColor, cfg.fieldId, cfg.name, cfg.compacto, cfg.permitirAgregar);
    nuevo.campoInput.value = viejo.campoInput.value;
    if (cfg.compacto) {                       // el del sidebar es un filtro
      nuevo.campoInput.addEventListener('change', applyFilters);
      nuevo.campoInput.addEventListener('input', applyFilters);
    }
    viejo.replaceWith(nuevo);
    nuevo.refresh();
  });
}

async function agregarColorNuevo(nombre, hex, fieldId) {
  try {
    const body = new FormData();
    body.append('campo', 'color');
    body.append('opcion', nombre);
    body.append('hex', hex);
    const resp = await fetch('/field/option', { method: 'POST', body });
    const data = await resp.json();
    if (!resp.ok || !data.ok) return data.error || 'No se pudo agregar el color.';
    const cfgResp = await fetch('/api/config');
    state.config = await cfgResp.json();
  } catch {
    return 'No se pudo conectar con el servidor.';
  }
  const campoColor = state.config.campos.find(c => c.nombre === 'color');
  const guardado = campoColor.opciones.find(o => normalizarTexto(o) === normalizarTexto(nombre)) || nombre;
  reemplazarColorPickers(campoColor);
  const input = document.getElementById(fieldId);
  if (input) input.value = guardado;
  refreshColorPickers();
  return null;
}

async function enviarHexColor(opcion, hex) {
  try {
    const body = new FormData();
    body.append('campo', 'color');
    body.append('opcion', opcion);
    body.append('hex', hex);
    const resp = await fetch('/field/option/color', { method: 'POST', body });
    const data = await resp.json();
    return resp.ok && data.ok;
  } catch {
    return false;
  }
}

// Sube a campos.json los hex que estaban en localStorage y los borra de ahí.
async function migrarHexLocales() {
  let mapa = null;
  try { mapa = JSON.parse(localStorage.getItem(HEX_KEY)); } catch { return; }
  if (!mapa || typeof mapa !== 'object') return;
  const campoColor = state.config.campos.find(c => c.nombre === 'color');
  if (!campoColor) return;
  const enServidor = new Set(Object.keys(campoColor.colores || {}).map(normalizarTexto));
  let subidos = 0;
  for (const [clave, hex] of Object.entries(mapa)) {
    const opcion = campoColor.opciones.find(o => normalizarTexto(o) === clave);
    if (!opcion) { delete mapa[clave]; continue; }          // la opción ya no existe
    if (!enServidor.has(clave)) {
      if (!(await enviarHexColor(opcion, hex))) continue;   // se reintenta en la próxima carga
      subidos++;
    }
    delete mapa[clave];
  }
  try {
    if (Object.keys(mapa).length) localStorage.setItem(HEX_KEY, JSON.stringify(mapa));
    else localStorage.removeItem(HEX_KEY);
  } catch { /* sin almacenamiento */ }
  if (subidos) {
    try { state.config = await (await fetch('/api/config')).json(); } catch { /* se ve en la próxima carga */ }
  }
}

let dialogoColor = null;

function abrirDialogoColor(alGuardar) {
  if (!dialogoColor) dialogoColor = crearDialogoColor();
  dialogoColor.abrir(alGuardar);
}

function crearDialogoColor() {
  const NS = 'http://www.w3.org/2000/svg';
  const dlg = document.createElement('dialog');
  dlg.className = 'dialogo-color';
  dlg.innerHTML = `
    <div class="modal">
      <div class="head">
        <div>
          <h2>Agregar color</h2>
          <p>Elige un tono en la paleta hexagonal o escribe el código hex.</p>
        </div>
        <button class="close" type="button" data-accion="cerrar">×</button>
      </div>
      <div class="content">
        <svg class="hex-paleta" role="img" aria-label="Paleta hexagonal de colores"></svg>
        <label for="hex-luz">Luminosidad</label>
        <input id="hex-luz" type="range" min="5" max="95" value="50">
        <label for="hex-valor">Hex</label>
        <div class="hex-fila">
          <input id="hex-valor" type="text" placeholder="#1f5fbf" maxlength="7" autocomplete="off">
          <span class="hex-muestra" id="hex-muestra"></span>
        </div>
        <label for="hex-nombre">Nombre del color</label>
        <input id="hex-nombre" type="text" placeholder="Ej. Azul petróleo" autocomplete="off">
        <div class="hex-error" id="hex-error"></div>
      </div>
      <div class="footer">
        <button class="btn primary" type="button" data-accion="guardar">Agregar color</button>
        <button class="btn secondary" type="button" data-accion="cerrar">Cancelar</button>
      </div>
    </div>`;
  document.body.appendChild(dlg);

  const svg = dlg.querySelector('.hex-paleta');
  const luz = dlg.querySelector('#hex-luz');
  const valor = dlg.querySelector('#hex-valor');
  const muestra = dlg.querySelector('#hex-muestra');
  const nombre = dlg.querySelector('#hex-nombre');
  const error = dlg.querySelector('#hex-error');
  const btnGuardar = dlg.querySelector('[data-accion="guardar"]');
  let alGuardarFn = null;

  function actualizarMuestra() {
    const hex = normalizarHex(valor.value);
    muestra.style.background = hex || '';
    valor.style.borderColor = (valor.value && !hex) ? 'var(--danger)' : '';
    svg.querySelectorAll('polygon').forEach(p => p.classList.toggle('sel', p.dataset.hex === hex));
  }

  function dibujar() {
    const N = 8, size = 15;                    // N anillos; size = radio de cada hexágono
    const w = Math.sqrt(3) * size;
    const maxD = w * N;
    const hw = w * N + size, hh = 1.5 * size * N + size;
    svg.setAttribute('viewBox', `${-hw} ${-hh} ${2 * hw} ${2 * hh}`);
    svg.replaceChildren();
    for (let r = -N; r <= N; r++) {
      for (let q = -N; q <= N; q++) {
        if (Math.abs(q + r) > N) continue;
        const x = w * (q + r / 2), y = 1.5 * size * r;
        let hue = Math.atan2(y, x) * 180 / Math.PI;
        if (hue < 0) hue += 360;
        const sat = Math.min(100, (Math.hypot(x, y) / maxD) * 100);
        const hex = hslAHex(hue, sat, Number(luz.value));
        const pts = [];
        for (let i = 0; i < 6; i++) {
          const a = (60 * i + 30) * Math.PI / 180;
          pts.push(`${(x + (size - 0.6) * Math.cos(a)).toFixed(2)},${(y + (size - 0.6) * Math.sin(a)).toFixed(2)}`);
        }
        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', pts.join(' '));
        poly.setAttribute('fill', hex);
        poly.dataset.hex = hex;
        poly.addEventListener('click', () => {
          valor.value = hex;
          error.textContent = '';
          actualizarMuestra();
        });
        svg.appendChild(poly);
      }
    }
    actualizarMuestra();
  }

  async function guardar() {
    const hex = normalizarHex(valor.value);
    const nom = nombre.value.trim();
    if (!hex) { error.textContent = 'Escribe un hex válido (por ejemplo #1f5fbf) o elige uno de la paleta.'; return; }
    if (!nom) { error.textContent = 'Ponle un nombre al color.'; return; }
    btnGuardar.disabled = true;
    const msg = await alGuardarFn(nom, hex);
    btnGuardar.disabled = false;
    if (msg) { error.textContent = msg; return; }
    dlg.close();
  }

  luz.addEventListener('input', dibujar);
  valor.addEventListener('input', () => { error.textContent = ''; actualizarMuestra(); });
  valor.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); nombre.focus(); } });
  nombre.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); guardar(); } });
  dlg.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-accion]');
    if (!btn) return;
    if (btn.dataset.accion === 'cerrar') dlg.close();
    else if (btn.dataset.accion === 'guardar') guardar();
  });

  return {
    abrir(fn) {
      alGuardarFn = fn;
      valor.value = '';
      nombre.value = '';
      error.textContent = '';
      luz.value = 50;
      dibujar();
      dlg.showModal();
    },
  };
}
//

function renderFormFields(containerSelector, campos, prefix) {
  const container = document.querySelector(containerSelector);
  container.innerHTML = '';
  for (const campo of campos) {
    const block = document.createElement('div');
    block.className = 'section';
    const fieldId = `${prefix}-${campo.nombre}`;
    const label = document.createElement('label');
    label.setAttribute('for', fieldId);
    label.textContent = `${campo.etiqueta}${campo.requerido ? ' *' : ''}`;
    block.appendChild(label);
    if (campo.tipo === 'lista' && campo.nombre === 'color') {
      block.appendChild(buildColorPicker(
        campo, fieldId,
        prefix === 'garment' ? `field_${campo.nombre}` : `batch_${campo.nombre}`,
        false,
        prefix === 'garment'
      ));
    }
    else if (campo.tipo === 'lista') {
      const select = document.createElement('select');
      select.id = fieldId;
      select.name = prefix === 'garment' ? `field_${campo.nombre}` : `batch_${campo.nombre}`;
      select.innerHTML = `<option value="">--</option>${(campo.opciones || []).map(op => `<option value="${escapeHtml(op)}">${escapeHtml(op)}</option>`).join('')}`;
      block.appendChild(select);
    } else {
      const input = document.createElement('input');
      input.id = fieldId;
      input.name = prefix === 'garment' ? `field_${campo.nombre}` : `batch_${campo.nombre}`;
      input.type = 'text';
      block.appendChild(input);
    }
    container.appendChild(block);
  }
}

function renderCard(prenda) {
  const article = document.createElement('article');
  article.className = 'panel card';
  const imgSrc = prenda.foto ? `/img/${encodeURIComponent(prenda.foto.split('/').pop())}` : '';
  article.innerHTML = `
    ${imgSrc ? `<img src="${imgSrc}" alt="${escapeHtml(prenda.identificador || 'Prenda')}">` : `<div class="ph"></div>`}
    <div class="body">
      <h3>${escapeHtml(prenda.identificador || 'Sin identificador')}</h3>
      <div class="badges">${state.config.campos.map(campo => prenda[campo.nombre] ? `<span class="badge">${escapeHtml(campo.etiqueta)}:${escapeHtml(prenda[campo.nombre])}</span>` : '').join('')}</div>
      ${prenda.comentarios ? `<div class="muted" style="font-size:.9rem;">${escapeHtml(prenda.comentarios)}</div>` : ''}
      <div class="tools">
        <button class="btn secondary" type="button">Editar</button>
        <button class="btn danger" type="button">Borrar</button>
      </div>
    </div>
  `;
  const portada = article.querySelector('img, .ph');
  if (portada) portada.addEventListener('click', () => openEditModal(prenda));   // con muchas columnas se edita tocando la foto
  const [editBtn, deleteBtn] = article.querySelectorAll('button');
  editBtn.addEventListener('click', () => openEditModal(prenda));
  deleteBtn.addEventListener('click', () => deletePrenda(prenda));
  return article;
}

async function openEditModal(prenda) {
  state.editId = prenda.id;
  $('#garment-title').textContent = 'Editar prenda';
  $('#garment-subtitle').textContent = 'Modifica los campos o reemplaza la foto.';
  $('#garment-record-id').value = prenda.id;
  $('#garment-current-photo').value = prenda.foto || '';
  $('#garment-identificador').value = prenda.identificador || '';
  $('#garment-comentarios').value = prenda.comentarios || '';
  $('#garment-return-query').value = window.location.search; 
  $('#delete-garment').classList.remove('hidden');
  for (const campo of state.config.campos) {
    const el = document.querySelector(`#garment-${campo.nombre}`);
    if (el) el.value = prenda[campo.nombre] || '';
  }
  refreshColorPickers();
  $('#garment-preview').src = prenda.foto ? `/img/${encodeURIComponent(prenda.foto.split('/').pop())}` : '';
  openDialog('garment-dialog');
}

function openCreateModal() {
  state.editId = null;
  $('#garment-title').textContent = 'Nueva prenda';
  $('#garment-subtitle').textContent = 'Crea una prenda nueva desde el popup.';
  $('#garment-form').reset();
  document.querySelectorAll('#garment-fields .color-picker input[type="hidden"]').forEach(i => { i.value = ''; });
  refreshColorPickers();
  $('#garment-record-id').value = '';
  $('#garment-current-photo').value = '';
  $('#garment-return-query').value = window.location.search; 
  $('#garment-preview').removeAttribute('src');
  $('#delete-garment').classList.add('hidden');
  openDialog('garment-dialog');
}

function initFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const filters = {};
  const q = params.get('q');
  if (q) {
    $('#q').value = q;
    filters.q = q;
  }
  if (state.config && state.config.campos) {
    for (const campo of state.config.campos) {
      const val = params.get(campo.nombre);
      if (val) {
        const control = $(`#filter-${campo.nombre}`);
        if (control) control.value = val;
        filters[campo.nombre] = val;
      }
    }
  }
  refreshColorPickers();   // marca el color que venga en la URL
  state.filters = filters;
}
function deletePrenda(prenda) {
  if (!confirm(`¿Borrar definitivamente ${prenda.identificador || 'esta prenda'}?`)) return;
  const form = document.createElement('form');
  form.method = 'post';
  form.action = '/delete';
  const input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'record_id';
  input.value = prenda.id;
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
}

function wireModalPreviews() {
  $('#garment-foto').addEventListener('change', () => {
    const file = $('#garment-foto').files[0];
    if (file) $('#garment-preview').src = URL.createObjectURL(file);
  });
  $('#batch-fotos').addEventListener('change', () => {
    const container = $('#batch-preview');
    container.innerHTML = '';
    [...$('#batch-fotos').files].forEach(file => {
      const item = document.createElement('div');
      item.className = 'preview-item';
      item.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="${escapeHtml(file.name)}"><div class="muted" style="font-size:.88rem;">${escapeHtml(file.name)}</div>`;
      container.appendChild(item);
    });
  });
}

$('#filters-form').addEventListener('submit', applyFilters);
$('#clear-filters').addEventListener('click', () => {
  $('#filters-form').reset();
  document.querySelectorAll('#dynamic-filters .color-picker input[type="hidden"]').forEach(i => { i.value = ''; });
  refreshColorPickers();
  state.filters = {};
  loadPrendas();
});
$('#refresh-btn').addEventListener('click', loadPrendas);
$('#open-add').addEventListener('click', openCreateModal);
$('#open-batch').addEventListener('click', () => openDialog('batch-dialog'));
$('#open-field').addEventListener('click', () => openDialog('field-dialog'));
$('#add-season-option').addEventListener('click', addSeasonOption);
$('#delete-garment').addEventListener('click', () => {
  const form = document.createElement('form');
  form.method = 'post';
  form.action = '/delete';
  const input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'record_id';
  input.value = $('#garment-record-id').value;
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
});

wireModalPreviews();
$('#garment-form').addEventListener('submit', () => {
  const params = new URLSearchParams($('#garment-return-query').value.replace(/^\?/, ''));
  for (const campo of state.config.campos) {
    if (!params.has(campo.nombre)) continue;
    const filtro = normalizarTexto(params.get(campo.nombre));
    const nuevo = normalizarTexto(document.getElementById(`garment-${campo.nombre}`)?.value);
    const cumple = campo.tipo === 'lista' ? nuevo === filtro : nuevo.includes(filtro);
    if (!cumple) params.delete(campo.nombre);
  }
  if (params.has('q')) {
    const q = normalizarTexto(params.get('q'));
    const texto = normalizarTexto($('#garment-identificador').value + ' ' + $('#garment-comentarios').value);
    if (!texto.includes(q)) params.delete('q');
  }
  const qs = params.toString();
  $('#garment-return-query').value = qs ? '?' + qs : '';
});

// --- Cajón de filtros (celular) y botón flotante (+) ---
const fabWrap = $('#fab-wrap');
function setFab(open) {
  fabWrap.classList.toggle('open', open);
  $('#fab').setAttribute('aria-expanded', String(open));
}
function setSidebar(open) {
  document.body.classList.toggle('sidebar-open', open);
  $('#toggle-sidebar').setAttribute('aria-expanded', String(open));
}
$('#fab').addEventListener('click', () => setFab(!fabWrap.classList.contains('open')));
$('#fab-scrim').addEventListener('click', () => setFab(false));
fabWrap.querySelectorAll('.fab-item').forEach(btn => btn.addEventListener('click', () => setFab(false)));
$('#toggle-sidebar').addEventListener('click', () => setSidebar(true));
$('#close-sidebar').addEventListener('click', () => setSidebar(false));
$('#sidebar-scrim').addEventListener('click', () => setSidebar(false));
$('#filters-form').addEventListener('submit', () => setSidebar(false));
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { setFab(false); setSidebar(false); }
});

// --- Columnas de la grilla (n x n): el tamaño de las fotos se ajusta solo ---
const COLS_KEY = 'ropero.cols';
const maxCols = () => (window.innerWidth <= 900 ? 6 : 10);
function leerCols() {
  try {
    const v = parseInt(localStorage.getItem(COLS_KEY), 10);
    if (v >= 1) return v;
  } catch { /* sin almacenamiento */ }
  return window.innerWidth <= 900 ? 2 : 5;
}
let cols = leerCols();
function aplicarCols(n, guardar = false) {
  cols = Math.min(Math.max(1, n), maxCols());
  const grid = $('#card-grid');
  grid.style.setProperty('--cols', cols);
  grid.dataset.densidad = cols <= 3 ? 'completa' : cols <= 5 ? 'media' : 'minima';
  $('#cols-value').textContent = cols;
  $('#cols-menos').disabled = cols <= 1;
  $('#cols-mas').disabled = cols >= maxCols();
  if (guardar) {
    try { localStorage.setItem(COLS_KEY, String(cols)); } catch { /* ignorar */ }
  }
}
$('#cols-menos').addEventListener('click', () => aplicarCols(cols - 1, true));
$('#cols-mas').addEventListener('click', () => aplicarCols(cols + 1, true));
window.addEventListener('resize', () => aplicarCols(cols));
aplicarCols(cols);

loadConfig();

// --- PWA: el service worker solo se registra en contexto seguro (HTTPS o localhost) ---
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('/sw.js').catch(() => { /* sin soporte: la web sigue funcionando */ });
}
