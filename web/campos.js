(() => {
  const $ = (s) => document.querySelector(s);
  const estado = { campos: [], campo: null, opciones: [], abierta: null };

  const norm = (s) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
  const plural = (n) => `${n} ${n === 1 ? "prenda" : "prendas"}`;

  function aviso(texto, error = false) {
    const el = $("#estado");
    el.textContent = texto;
    el.className = "aviso" + (error ? " error" : "");
  }

  async function pedir(url, datos) {
    const opts = {};
    if (datos) {
      const fd = new FormData();
      Object.entries(datos).forEach(([k, v]) => fd.append(k, v));
      Object.assign(opts, { method: "POST", body: fd });
    }
    const r = await fetch(url, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || "Error inesperado.");
    return j;
  }

  function el(tag, props = {}, ...hijos) {
    const e = Object.assign(document.createElement(tag), props);
    hijos.forEach((h) => e.append(h));
    return e;
  }

  function boton(texto, clase, onclick, extra = {}) {
    return el("button", { type: "button", className: "btn " + clase, textContent: texto, onclick, ...extra });
  }

  async function ejecutar(url, datos, mensaje) {
    try {
      const j = await pedir(url, datos);
      estado.abierta = null;
      await cargarOpciones();
      aviso(typeof mensaje === "function" ? mensaje(j) : mensaje);
    } catch (e) {
      aviso(e.message, true);
    }
  }

  // --- Paneles de acción por opción ---------------------------------------
  function panelRenombrar(op) {
    const input = el("input", { type: "text", value: op.valor, id: "renombrar-input" });
    const pista = el("p", { className: "hint" });
    const actualizar = () => {
      const nuevo = input.value.trim();
      const otra = estado.opciones.find((o) => o.valor !== op.valor && norm(o.valor) === norm(nuevo));
      pista.textContent = otra
        ? `«${otra.valor}» ya existe: se moverán ${plural(op.prendas)} a esa opción y «${op.valor}» desaparecerá.`
        : "";
    };
    input.oninput = actualizar;
    const guardar = () =>
      ejecutar(
        "/field/option/rename",
        { campo: estado.campo, origen: op.valor, nuevo: input.value.trim() },
        (j) => (j.fusion ? `«${j.origen}» se fusionó con «${j.destino}» (${plural(j.movidas)}).` : `Renombrada a «${j.destino}».`)
      );
    input.onkeydown = (ev) => ev.key === "Enter" && (ev.preventDefault(), guardar());
    actualizar();
    queueMicrotask(() => input.focus());
    return el(
      "div",
      { className: "panel-accion" },
      el("label", { htmlFor: "renombrar-input", textContent: "Nuevo nombre" }),
      input,
      pista,
      el("div", { className: "fila" }, boton("Guardar", "primary", guardar), boton("Cancelar", "secondary", cerrarPanel))
    );
  }

  function panelFusionar(op) {
    const otras = estado.opciones.filter((o) => o.valor !== op.valor);
    const select = el("select", { id: "fusionar-select" }, ...otras.map((o) => el("option", { value: o.valor, textContent: o.valor })));
    const pista = el("p", { className: "hint" });
    const actualizar = () => {
      pista.textContent = `Se moverán ${plural(op.prendas)} a «${select.value}» y «${op.valor}» desaparecerá.`;
    };
    select.onchange = actualizar;
    actualizar();
    return el(
      "div",
      { className: "panel-accion" },
      el("label", { htmlFor: "fusionar-select", textContent: "Fusionar con" }),
      select,
      pista,
      el(
        "div",
        { className: "fila" },
        boton("Fusionar", "primary", () =>
          ejecutar("/field/option/merge", { campo: estado.campo, origen: op.valor, destino: select.value }, (j) => `«${j.origen}» se fusionó con «${j.destino}» (${plural(j.movidas)}).`)
        ),
        boton("Cancelar", "secondary", cerrarPanel)
      )
    );
  }

  function panelEliminar(op) {
    return el(
      "div",
      { className: "panel-accion" },
      el("p", { textContent: `¿Eliminar «${op.valor}»? No tiene prendas asignadas.` }),
      el(
        "div",
        { className: "fila" },
        boton("Eliminar", "danger", () => ejecutar("/field/option/delete", { campo: estado.campo, origen: op.valor }, `«${op.valor}» eliminada.`)),
        boton("Cancelar", "secondary", cerrarPanel)
      )
    );
  }

  function cerrarPanel() {
    estado.abierta = null;
    pintarLista();
  }

  function abrir(valor, accion) {
    estado.abierta = { valor, accion };
    pintarLista();
  }

  // --- Pintado ------------------------------------------------------------
  function pintarLista() {
    const cont = $("#lista");
    cont.replaceChildren();
    $("#vacio").classList.toggle("hidden", estado.opciones.length > 0);

    estado.opciones.forEach((op) => {
      const enUso = op.prendas > 0;
      const acciones = el(
        "div",
        { className: "acciones" },
        boton("Renombrar", "secondary", () => abrir(op.valor, "renombrar")),
        boton("Fusionar", "secondary", () => abrir(op.valor, "fusionar"), { disabled: estado.opciones.length < 2 }),
        boton("Eliminar", "danger", () => abrir(op.valor, "eliminar"), { disabled: enUso })
      );
      const fila = el(
        "div",
        { className: "fila" },
        el("span", { className: "nombre", textContent: op.valor }),
        el("span", { className: "conteo", textContent: plural(op.prendas) }),
        acciones
      );
      const item = el("div", { className: "opcion" }, fila);
      if (enUso) item.append(el("p", { className: "hint", textContent: "Para eliminarla, fusiónala con otra opción o reasigna sus prendas." }));

      const a = estado.abierta;
      if (a && a.valor === op.valor) {
        item.append(a.accion === "renombrar" ? panelRenombrar(op) : a.accion === "fusionar" ? panelFusionar(op) : panelEliminar(op));
      }
      cont.append(item);
    });
  }

  function pintarSelector() {
    const nav = $("#selector");
    nav.replaceChildren();
    estado.campos.forEach((c) => {
      const b = boton(c.etiqueta || c.nombre, "secondary", () => {
        location.hash = c.nombre;
        seleccionar(c.nombre);
      });
      if (c.nombre === estado.campo) b.setAttribute("aria-current", "true");
      nav.append(b);
    });
  }

  async function cargarOpciones() {
    const j = await pedir(`/api/campos/opciones?campo=${encodeURIComponent(estado.campo)}`);
    estado.opciones = j.opciones;
    $("#titulo").textContent = `Opciones de ${j.etiqueta}`;
    pintarLista();
  }

  async function seleccionar(nombre) {
    estado.campo = nombre;
    estado.abierta = null;
    pintarSelector();
    aviso("");
    try {
      await cargarOpciones();
    } catch (e) {
      aviso(e.message, true);
    }
  }

  $("#alta").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = $("#alta-nombre");
    const opcion = input.value.trim();
    if (!opcion) return;
    try {
      await pedir("/field/option", { campo: estado.campo, opcion });
      input.value = "";
      await cargarOpciones();
      aviso(`«${opcion}» agregada.`);
    } catch (e) {
      aviso(e.message, true);
    }
  });

  (async function iniciar() {
    try {
      const cfg = await pedir("/api/config");
      estado.campos = cfg.campos.filter((c) => c.tipo === "lista");
      if (!estado.campos.length) return aviso("No hay campos de tipo lista.", true);
      const pedido = decodeURIComponent(location.hash.slice(1));
      const inicial = estado.campos.find((c) => c.nombre === pedido) || estado.campos[0];
      await seleccionar(inicial.nombre);
    } catch (e) {
      aviso(e.message, true);
    }
  })();
})();