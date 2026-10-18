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
  if (COLORES_CSS[n]) return COLORES_CSS[n];
  // Aproximación por primera palabra ("verde lima" -> verde)
  const primera = n.split(/\s+/)[0];
  return COLORES_CSS[primera] || null;
}


function buildColorPicker(campo, fieldId, name, compacto = false) {
  const root = document.createElement('div');
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
  root.campoInput = hidden;      // antes: root.hidden (propiedad nativa del DOM)
  root.append(hidden, search, status, grid, empty);
  refresh();
  return root;
}

function refreshColorPickers() {
  document.querySelectorAll('.color-picker').forEach(p => p.refresh());
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
        prefix === 'garment' ? `field_${campo.nombre}` : `batch_${campo.nombre}`
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

loadConfig();

