/* CódigoLocal — Cliente Web UI modular (sin dependencias externas, seguro contra XSS) */

const state = {
  settings: null,
  providersInfo: null,
  sessions: [],
  activeSessionId: null,
  messages: [],
  changes: [],
  treeData: null,
  attachedFiles: [],
  proposalsById: new Map(),
  inspectedDiff: null,
  inspectedFile: null,
  diffMode: "unified",
  streaming: false,
  activeRunId: null,
  abortController: null,
  setupTab: "legacy_i5_1gb",
  browseCurrent: null,
  browseParent: null,
};

const ACTION_LABELS = {
  create: "Crear",
  edit: "Editar",
  write: "Reemplazar",
  delete: "Eliminar",
};

const STATUS_LABELS = {
  pending: "Pendiente",
  applied: "Aplicado",
  rejected: "Rechazado",
  reverted: "Revertido",
  error: "Error",
};

function $(id) {
  return document.getElementById(id);
}

async function apiJson(url, options = {}) {
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return resp.json();
}

function createSvgIcon(kind) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  if (kind === "folder") {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", "M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z");
    svg.appendChild(p);
  } else if (kind === "file") {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z");
    const l = document.createElementNS(ns, "polyline");
    l.setAttribute("points", "14 2 14 8 20 8");
    svg.append(p, l);
  } else if (kind === "plus") {
    const l1 = document.createElementNS(ns, "line");
    l1.setAttribute("x1", "12");
    l1.setAttribute("y1", "5");
    l1.setAttribute("x2", "12");
    l1.setAttribute("y2", "19");
    const l2 = document.createElementNS(ns, "line");
    l2.setAttribute("x1", "5");
    l2.setAttribute("y1", "12");
    l2.setAttribute("x2", "19");
    l2.setAttribute("y2", "12");
    svg.append(l1, l2);
  } else if (kind === "trash") {
    const p = document.createElementNS(ns, "polyline");
    p.setAttribute("points", "3 6 5 6 21 6");
    const p2 = document.createElementNS(ns, "path");
    p2.setAttribute("d", "M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6");
    svg.append(p, p2);
  }
  return svg;
}

function copyText(text, btn) {
  if (!navigator.clipboard) return;
  navigator.clipboard.writeText(text).then(() => {
    if (!btn) return;
    const prev = btn.textContent;
    btn.textContent = "Copiado";
    setTimeout(() => {
      btn.textContent = prev;
    }, 1200);
  }).catch(() => {});
}

function basename(pathStr) {
  if (!pathStr) return "Workspace";
  const parts = pathStr.replace(/[/\\]+$/, "").split(/[/\\]/);
  return parts[parts.length - 1] || pathStr;
}

/* ---------------- Renderizador Markdown seguro ---------------- */

function appendInlineMarkdown(parent, lineText) {
  const tokenRe = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIdx = 0;
  let match;
  while ((match = tokenRe.exec(lineText)) !== null) {
    if (match.index > lastIdx) {
      parent.appendChild(document.createTextNode(lineText.slice(lastIdx, match.index)));
    }
    const tok = match[0];
    if (tok.startsWith("`") && tok.endsWith("`")) {
      const code = document.createElement("code");
      code.textContent = tok.slice(1, -1);
      parent.appendChild(code);
    } else if (tok.startsWith("**") && tok.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = tok.slice(2, -2);
      parent.appendChild(strong);
    } else if (tok.startsWith("*") && tok.endsWith("*")) {
      const em = document.createElement("em");
      em.textContent = tok.slice(1, -1);
      parent.appendChild(em);
    }
    lastIdx = match.index + tok.length;
  }
  if (lastIdx < lineText.length) {
    parent.appendChild(document.createTextNode(lineText.slice(lastIdx)));
  }
}

function renderSafeMarkdown(container, rawText) {
  container.textContent = "";
  const text = (rawText || "").replace(/\r\n/g, "\n");
  const segments = text.split(/(```[\s\S]*?```)/g);

  for (const seg of segments) {
    if (!seg) continue;
    if (seg.startsWith("```") && seg.endsWith("```") && seg.length >= 6) {
      const inner = seg.slice(3, -3);
      const nlIdx = inner.indexOf("\n");
      const lang = nlIdx >= 0 ? inner.slice(0, nlIdx).trim() : "";
      const codeText = nlIdx >= 0 ? inner.slice(nlIdx + 1) : inner;

      const block = document.createElement("div");
      block.className = "code-block";
      const head = document.createElement("div");
      head.className = "code-block-head";
      const langSpan = document.createElement("span");
      langSpan.textContent = lang || "código";
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "ghost-btn compact-btn";
      copyBtn.textContent = "Copiar";
      copyBtn.addEventListener("click", () => copyText(codeText, copyBtn));
      head.append(langSpan, copyBtn);

      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeText;
      pre.appendChild(code);
      block.append(head, pre);
      container.appendChild(block);
      continue;
    }

    const lines = seg.split("\n");
    let listEl = null;
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        listEl = null;
        continue;
      }
      if (/^#{1,3}\s+/.test(trimmed)) {
        listEl = null;
        const level = trimmed.match(/^(#{1,3})/)[1].length;
        const h = document.createElement(level === 1 ? "h2" : level === 2 ? "h3" : "h4");
        appendInlineMarkdown(h, trimmed.replace(/^#{1,3}\s+/, ""));
        container.appendChild(h);
        continue;
      }
      if (/^[-*]\s+/.test(trimmed)) {
        if (!listEl || listEl.tagName !== "UL") {
          listEl = document.createElement("ul");
          container.appendChild(listEl);
        }
        const li = document.createElement("li");
        appendInlineMarkdown(li, trimmed.replace(/^[-*]\s+/, ""));
        listEl.appendChild(li);
        continue;
      }
      if (/^\d+\.\s+/.test(trimmed)) {
        if (!listEl || listEl.tagName !== "OL") {
          listEl = document.createElement("ol");
          container.appendChild(listEl);
        }
        const li = document.createElement("li");
        appendInlineMarkdown(li, trimmed.replace(/^\d+\.\s+/, ""));
        listEl.appendChild(li);
        continue;
      }
      listEl = null;
      const p = document.createElement("p");
      appendInlineMarkdown(p, line);
      container.appendChild(p);
    }
  }
}

/* ---------------- Renderizador de Diffs ---------------- */

function renderDiffRows(container, hunks, mode = "unified") {
  container.textContent = "";
  if (!hunks || hunks.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-inspector";
    empty.textContent = "Sin diferencias de texto.";
    container.appendChild(empty);
    return;
  }

  if (mode === "split") {
    const grid = document.createElement("div");
    grid.className = "split-diff-grid";

    let i = 0;
    while (i < hunks.length) {
      const row = hunks[i];
      if (row.type === "hunk") {
        const cell = document.createElement("div");
        cell.className = "split-cell is-hunk";
        cell.textContent = row.text;
        grid.appendChild(cell);
        i++;
        continue;
      }
      if (row.type === "context") {
        grid.append(
          makeSplitCell(row.old_line, row.text, "context"),
          makeSplitCell(row.new_line, row.text, "context")
        );
        i++;
        continue;
      }
      const dels = [];
      while (i < hunks.length && hunks[i].type === "del") {
        dels.push(hunks[i]);
        i++;
      }
      const adds = [];
      while (i < hunks.length && hunks[i].type === "add") {
        adds.push(hunks[i]);
        i++;
      }
      const maxLen = Math.max(dels.length, adds.length);
      for (let k = 0; k < maxLen; k++) {
        const d = dels[k];
        const a = adds[k];
        grid.append(
          d ? makeSplitCell(d.old_line, d.text, "del") : makeSplitCell("", "", "empty"),
          a ? makeSplitCell(a.new_line, a.text, "add") : makeSplitCell("", "", "empty")
        );
      }
    }
    container.appendChild(grid);
    return;
  }

  for (const row of hunks) {
    const lineEl = document.createElement("div");
    lineEl.className = `diff-line is-${row.type}`;
    const oldSpan = document.createElement("span");
    oldSpan.className = "diff-ln";
    oldSpan.textContent = row.old_line != null ? String(row.old_line) : "";

    const newSpan = document.createElement("span");
    newSpan.className = "diff-ln";
    newSpan.textContent = row.new_line != null ? String(row.new_line) : "";

    const signSpan = document.createElement("span");
    signSpan.className = "diff-sign";
    signSpan.textContent = row.type === "add" ? "+" : row.type === "del" ? "-" : row.type === "hunk" ? "@@" : " ";

    const textSpan = document.createElement("span");
    textSpan.textContent = row.text;

    lineEl.append(oldSpan, newSpan, signSpan, textSpan);
    container.appendChild(lineEl);
  }
}

function makeSplitCell(ln, text, type) {
  const cell = document.createElement("div");
  cell.className = `split-cell is-${type}`;
  const lnEl = document.createElement("span");
  lnEl.className = "diff-ln";
  lnEl.textContent = ln != null && ln !== "" ? String(ln) : "";
  const txtEl = document.createElement("span");
  txtEl.textContent = text;
  cell.append(lnEl, txtEl);
  return cell;
}

/* ---------------- Barra superior y Proveedores ---------------- */

function updateTopBarFromSettings() {
  if (!state.settings) return;
  $("workspace-label").textContent = basename(state.settings.workspace_path);
  $("workspace-label").title = state.settings.workspace_path;
  $("select-provider").value = state.settings.provider;

  const profiles = state.providersInfo?.hardware_profiles || {};
  const prof = profiles[state.settings.hardware_profile];
  $("profile-short-label").textContent = prof ? prof.short_label : state.settings.hardware_profile;
  $("context-budget-label").textContent = `~0 / ${state.settings.num_ctx} tok`;
  populateModelSelect();
}

function populateModelSelect() {
  const select = $("select-model");
  select.textContent = "";
  const providerId = state.settings?.provider || "ollama";
  const prov = state.providersInfo?.providers?.[providerId];
  const installed = prov?.models || [];
  const seen = new Set();

  if (installed.length > 0) {
    const grp = document.createElement("optgroup");
    grp.label = "Modelos detectados en local";
    for (const m of installed) {
      seen.add(m.id);
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.size_mb ? `${m.id} (${m.size_mb} MB)` : m.id;
      grp.appendChild(opt);
    }
    select.appendChild(grp);
  }

  const recs = state.providersInfo?.recommended_models || [];
  const recGroup = document.createElement("optgroup");
  recGroup.label = "Recomendados (i5 1ra Gen · 1 GB)";
  for (const r of recs) {
    if (seen.has(r.id)) continue;
    seen.add(r.id);
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = `${r.id} (${r.vram_fit})`;
    recGroup.appendChild(opt);
  }
  if (recGroup.children.length > 0) select.appendChild(recGroup);

  const cur = state.settings?.model;
  if (cur && !seen.has(cur)) {
    const opt = document.createElement("option");
    opt.value = cur;
    opt.textContent = cur;
    select.prepend(opt);
  }
  if (cur) select.value = cur;
}

function updateStatusPill() {
  const pill = $("btn-status-pill");
  const txt = $("status-pill-text");
  const info = state.providersInfo;
  if (!info) return;
  const activeProv = info.providers?.[state.settings?.provider || "ollama"];
  if (activeProv?.online) {
    pill.classList.remove("is-offline");
    pill.classList.add("is-online");
    txt.textContent = `${activeProv.name} listo`;
  } else if (info.any_online) {
    const onlineNames = Object.values(info.providers).filter((p) => p.online).map((p) => p.name);
    pill.classList.remove("is-offline");
    pill.classList.add("is-online");
    txt.textContent = `Activo: ${onlineNames[0]}`;
  } else {
    pill.classList.remove("is-online");
    pill.classList.add("is-offline");
    txt.textContent = "Sin motor local";
  }
}

async function refreshProviders() {
  try {
    state.providersInfo = await apiJson("/api/providers/status");
    updateStatusPill();
    updateTopBarFromSettings();
    if (state.messages.length === 0) renderChatMessages();
  } catch (err) {
    console.error("Error consultando proveedores:", err);
  }
}

/* ---------------- Árbol de archivos y Visor ---------------- */

async function refreshFileTree() {
  try {
    state.treeData = await apiJson("/api/workspace/tree?depth=3");
    renderFileTree();
  } catch (err) {
    $("file-tree").textContent = `Error: ${err.message}`;
  }
}

function renderFileTree() {
  const container = $("file-tree");
  container.textContent = "";
  const filter = ($("input-file-filter").value || "").trim().toLowerCase();
  const nodes = state.treeData?.tree || [];

  if (nodes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-inspector";
    empty.textContent = "Esta carpeta no tiene archivos visibles.";
    container.appendChild(empty);
    return;
  }

  function renderNodes(items, depth) {
    for (const node of items) {
      if (node.type === "dir") {
        const matchesSelf = !filter || node.path.toLowerCase().includes(filter);
        const childMatches = filter ? hasMatchingChild(node.children || [], filter) : true;
        if (!matchesSelf && !childMatches) continue;

        const row = createTreeRow(node, depth);
        const childWrap = document.createElement("div");
        let expanded = depth === 0 || Boolean(filter);
        childWrap.hidden = !expanded;
        row.addEventListener("click", () => {
          expanded = !expanded;
          childWrap.hidden = !expanded;
        });
        container.appendChild(row);
        container.appendChild(childWrap);
        renderNodesInto(node.children || [], depth + 1, childWrap);
      } else {
        if (filter && !node.path.toLowerCase().includes(filter)) continue;
        container.appendChild(createTreeRow(node, depth));
      }
    }
  }

  function renderNodesInto(items, depth, target) {
    for (const node of items) {
      if (node.type === "dir") {
        if (filter && !node.path.toLowerCase().includes(filter) && !hasMatchingChild(node.children || [], filter)) {
          continue;
        }
        const row = createTreeRow(node, depth);
        const childWrap = document.createElement("div");
        let expanded = Boolean(filter);
        childWrap.hidden = !expanded;
        row.addEventListener("click", () => {
          expanded = !expanded;
          childWrap.hidden = !expanded;
        });
        target.append(row, childWrap);
        renderNodesInto(node.children || [], depth + 1, childWrap);
      } else {
        if (filter && !node.path.toLowerCase().includes(filter)) continue;
        target.appendChild(createTreeRow(node, depth));
      }
    }
  }

  renderNodes(nodes, 0);
}

function hasMatchingChild(children, filter) {
  for (const ch of children) {
    if (ch.path.toLowerCase().includes(filter)) return true;
    if (ch.type === "dir" && hasMatchingChild(ch.children || [], filter)) return true;
  }
  return false;
}

function createTreeRow(node, depth) {
  const row = document.createElement("div");
  row.className = "tree-row";
  if (state.inspectedFile?.path === node.path) row.classList.add("is-active");
  row.style.paddingLeft = `${6 + depth * 12}px`;

  const label = document.createElement("div");
  label.className = "tree-label";
  label.appendChild(createSvgIcon(node.type === "dir" ? "folder" : "file"));
  const nameSpan = document.createElement("span");
  nameSpan.className = "tree-name";
  nameSpan.textContent = node.name;
  nameSpan.title = node.path;
  label.appendChild(nameSpan);
  row.appendChild(label);

  if (node.type === "file") {
    const attachBtn = document.createElement("button");
    attachBtn.type = "button";
    attachBtn.className = "tree-attach-btn";
    attachBtn.title = "Adjuntar al chat";
    attachBtn.appendChild(createSvgIcon("plus"));
    attachBtn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      attachFile(node.path);
    });
    row.appendChild(attachBtn);
    row.addEventListener("click", () => openFileInInspector(node.path));
  }
  return row;
}

function attachFile(relPath) {
  if (!state.attachedFiles.includes(relPath)) {
    state.attachedFiles.push(relPath);
    renderAttachedChips();
  }
  $("chat-input").focus();
}

function renderAttachedChips() {
  const wrap = $("attached-chips");
  wrap.textContent = "";
  if (state.attachedFiles.length === 0) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  for (const path of state.attachedFiles) {
    const pill = document.createElement("span");
    pill.className = "attach-pill";
    const txt = document.createElement("span");
    txt.textContent = `@${path}`;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.textContent = "×";
    rm.title = "Quitar archivo";
    rm.addEventListener("click", () => {
      state.attachedFiles = state.attachedFiles.filter((f) => f !== path);
      renderAttachedChips();
    });
    pill.append(txt, rm);
    wrap.appendChild(pill);
  }
}

async function openFileInInspector(relPath) {
  try {
    const data = await apiJson(`/api/workspace/file?path=${encodeURIComponent(relPath)}`);
    state.inspectedFile = data;
    openInspectorTab("file");
    renderFileTree();

    $("inspector-file-toolbar").hidden = false;
    $("inspector-file-path").textContent = data.path;
    $("inspector-file-lines").textContent = `${data.total_lines} líneas`;

    const body = $("inspector-file-body");
    body.textContent = "";
    const lines = (data.content || "").split(/\r?\n/);
    lines.forEach((ln, idx) => {
      const row = document.createElement("div");
      row.className = "code-viewer-line";
      const num = document.createElement("span");
      num.className = "diff-ln";
      num.textContent = String(idx + 1);
      const txt = document.createElement("span");
      txt.textContent = ln;
      row.append(num, txt);
      body.appendChild(row);
    });
  } catch (err) {
    $("inspector-file-toolbar").hidden = true;
    $("inspector-file-body").textContent = `No se pudo leer el archivo: ${err.message}`;
    openInspectorTab("file");
  }
}

/* ---------------- Sesiones e Historial de Cambios ---------------- */

async function refreshSessions() {
  const data = await apiJson("/api/sessions");
  state.sessions = data.sessions || [];
  renderSessions();
}

function renderSessions() {
  const list = $("session-list");
  list.textContent = "";
  if (state.sessions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-inspector";
    empty.textContent = "Aún no hay sesiones guardadas.";
    list.appendChild(empty);
    return;
  }
  for (const s of state.sessions) {
    const item = document.createElement("div");
    item.className = "list-item";
    if (s.id === state.activeSessionId) item.classList.add("is-active");

    const head = document.createElement("div");
    head.className = "list-item-head";
    const title = document.createElement("span");
    title.className = "list-item-title";
    title.textContent = s.title || "Sesión sin título";
    const del = document.createElement("button");
    del.type = "button";
    del.className = "icon-btn";
    del.title = "Eliminar sesión";
    del.appendChild(createSvgIcon("trash"));
    del.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      await apiJson(`/api/sessions/${s.id}`, { method: "DELETE" });
      if (state.activeSessionId === s.id) state.activeSessionId = null;
      await ensureActiveSession();
    });
    head.append(title, del);

    const meta = document.createElement("div");
    meta.className = "muted-meta mono-num";
    meta.textContent = `${s.model} · ${s.message_count ?? 0} mensajes`;

    item.append(head, meta);
    item.addEventListener("click", () => loadSession(s.id));
    list.appendChild(item);
  }
}

async function ensureActiveSession() {
  await refreshSessions();
  const saved = localStorage.getItem("codigolocal-session");
  const target =
    state.sessions.find((s) => s.id === state.activeSessionId) ||
    state.sessions.find((s) => s.id === saved) ||
    state.sessions[0];

  if (target) {
    await loadSession(target.id);
  } else {
    const created = await apiJson("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "Nueva sesión" }),
    });
    await refreshSessions();
    await loadSession(created.session.id);
  }
}

async function loadSession(sessionId) {
  const data = await apiJson(`/api/sessions/${sessionId}`);
  state.activeSessionId = sessionId;
  localStorage.setItem("codigolocal-session", sessionId);
  state.messages = data.messages || [];
  state.changes = data.changes || [];
  renderSessions();
  renderChangesList();
  renderChatMessages();
}

async function refreshChanges() {
  if (!state.activeSessionId) return;
  const data = await apiJson(`/api/sessions/${state.activeSessionId}/changes`);
  state.changes = data.changes || [];
  renderChangesList();
}

function renderChangesList() {
  const list = $("changes-list");
  list.textContent = "";
  if (state.changes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-inspector";
    empty.textContent = "Todavía no hay propuestas de cambio en esta sesión.";
    list.appendChild(empty);
    return;
  }

  for (const ch of state.changes) {
    const item = document.createElement("div");
    item.className = "list-item";

    const head = document.createElement("div");
    head.className = "list-item-head";
    const pathEl = document.createElement("span");
    pathEl.className = "list-item-title mono-path";
    pathEl.textContent = ch.file_path;
    const badge = document.createElement("span");
    badge.className = `badge badge-${ch.status}`;
    badge.textContent = STATUS_LABELS[ch.status] || ch.status;
    head.append(pathEl, badge);

    const sub = document.createElement("div");
    sub.className = "inline-actions";
    const stats = document.createElement("span");
    stats.className = "diff-stats mono-num";
    stats.innerHTML = `<span class="stat-add">+${ch.added_lines}</span><span class="stat-del">-${ch.removed_lines}</span>`;

    const viewBtn = document.createElement("button");
    viewBtn.type = "button";
    viewBtn.className = "ghost-btn compact-btn";
    viewBtn.textContent = "Ver diff";
    viewBtn.addEventListener("click", () => openDiffInInspector(ch));

    sub.append(stats, viewBtn);

    if (ch.status === "applied") {
      const revBtn = document.createElement("button");
      revBtn.type = "button";
      revBtn.className = "ghost-btn compact-btn";
      revBtn.textContent = "Revertir";
      revBtn.addEventListener("click", () => revertChangeById(ch.id));
      sub.appendChild(revBtn);
    }

    item.append(head, sub);
    list.appendChild(item);
  }
}

/* ---------------- Chat y Estado Inicial ---------------- */

function renderChatMessages() {
  const container = $("chat-messages");
  container.textContent = "";

  if (state.messages.length === 0) {
    container.appendChild(buildEmptyWorkbench());
    return;
  }

  for (const msg of state.messages) {
    container.appendChild(buildMessageElement(msg));
  }
  container.scrollTop = container.scrollHeight;
}

function buildEmptyWorkbench() {
  const wrap = document.createElement("div");
  wrap.className = "empty-workbench";

  const anyOnline = Boolean(state.providersInfo?.any_online);
  if (!anyOnline) {
    const h1 = document.createElement("h1");
    h1.textContent = "Conecta un motor de IA local gratuito";
    const desc = document.createElement("p");
    desc.textContent =
      "No se detectó ningún servidor local activo en este equipo. Elige tu motor según tu procesador y tarjeta gráfica:";
    wrap.append(h1, desc);

    const tabs = document.createElement("div");
    tabs.className = "setup-tabs";
    const guides = state.providersInfo?.setup_guides || {};
    const tabOrder = [
      ["legacy_i5_1gb", "Intel i5 1ra Gen + NVIDIA 1 GB (Sin AVX)"],
      ["ollama", "Ollama"],
      ["lmstudio", "LM Studio"],
    ];
    for (const [key, label] of tabOrder) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `setup-tab-btn${state.setupTab === key ? " is-active" : ""}`;
      b.textContent = label;
      b.addEventListener("click", () => {
        state.setupTab = key;
        renderChatMessages();
      });
      tabs.appendChild(b);
    }
    wrap.appendChild(tabs);

    const activeGuide = guides[state.setupTab];
    if (activeGuide) {
      const sum = document.createElement("p");
      sum.textContent = activeGuide.summary;
      wrap.appendChild(sum);

      const cmdList = document.createElement("div");
      cmdList.className = "cmd-list";
      for (const item of activeGuide.commands || []) {
        const row = document.createElement("div");
        row.className = "cmd-row";
        const rHead = document.createElement("div");
        rHead.className = "cmd-row-head";
        const lbl = document.createElement("span");
        lbl.textContent = item.label;
        const cbtn = document.createElement("button");
        cbtn.type = "button";
        cbtn.className = "ghost-btn compact-btn";
        cbtn.textContent = "Copiar";
        cbtn.addEventListener("click", () => copyText(item.cmd, cbtn));
        rHead.append(lbl, cbtn);

        const code = document.createElement("code");
        code.textContent = item.cmd;
        row.append(rHead, code);
        cmdList.appendChild(row);
      }
      wrap.appendChild(cmdList);
    }

    const models = state.providersInfo?.recommended_models || [];
    if (models.length > 0) {
      const table = document.createElement("table");
      table.className = "model-table";
      table.innerHTML =
        "<thead><tr><th>Modelo recomendado</th><th>Tamaño</th><th>Ajuste en 1 GB VRAM</th></tr></thead>";
      const tbody = document.createElement("tbody");
      for (const m of models) {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td");
        td1.className = "mono-path";
        td1.textContent = m.id;
        const td2 = document.createElement("td");
        td2.className = "mono-num";
        td2.textContent = `${m.size_mb} MB`;
        const td3 = document.createElement("td");
        td3.textContent = m.vram_fit;
        tr.append(td1, td2, td3);
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      wrap.appendChild(table);
    }

    const actions = document.createElement("div");
    actions.className = "starter-chips";
    const retryBtn = document.createElement("button");
    retryBtn.type = "button";
    retryBtn.className = "primary-btn";
    retryBtn.textContent = "Comprobar conexión de nuevo";
    retryBtn.addEventListener("click", refreshProviders);
    actions.appendChild(retryBtn);
    wrap.appendChild(actions);
    return wrap;
  }

  const h1 = document.createElement("h1");
  h1.textContent = "Listo para analizar y editar tu proyecto";
  const p = document.createElement("p");
  p.textContent =
    "El agente inspeccionará tus archivos reales dentro del workspace y siempre te mostrará un diff antes de modificar código.";
  wrap.append(h1, p);

  const starters = [
    "Explora la arquitectura general de este proyecto",
    "Busca posibles errores o mejoras en el código",
    "Crea un módulo pequeño con pruebas unitarias",
    "Explica qué hace el archivo principal",
  ];
  const chips = document.createElement("div");
  chips.className = "starter-chips";
  for (const promptText of starters) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-btn";
    btn.textContent = promptText;
    btn.addEventListener("click", () => {
      $("chat-input").value = promptText;
      sendChatMessage();
    });
    chips.appendChild(btn);
  }
  wrap.appendChild(chips);
  return wrap;
}

function buildMessageElement(msg) {
  const block = document.createElement("div");
  block.className = `message-block ${msg.role === "user" ? "is-user" : "is-assistant"}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";

  if (msg.role === "user") {
    const attached = msg.metadata?.attached_files || [];
    if (attached.length > 0) {
      const strip = document.createElement("div");
      strip.className = "msg-attachments";
      for (const f of attached) {
        const pill = document.createElement("span");
        pill.className = "attach-pill";
        pill.textContent = `@${f}`;
        strip.appendChild(pill);
      }
      bubble.appendChild(strip);
    }
    const p = document.createElement("div");
    p.textContent = msg.content;
    p.style.whiteSpace = "pre-wrap";
    bubble.appendChild(p);
    block.appendChild(bubble);
    return block;
  }

  const tools = msg.metadata?.tools || [];
  if (tools.length > 0) {
    block.appendChild(buildToolTraceDetails(tools));
  }

  const md = document.createElement("div");
  md.className = "md-body";
  renderSafeMarkdown(md, msg.content);
  bubble.appendChild(md);
  block.appendChild(bubble);

  if (msg.metadata?.tok_per_sec) {
    const meta = document.createElement("div");
    meta.className = "message-meta mono-num";
    meta.textContent = `${msg.metadata.tokens_generated || 0} tok · ${msg.metadata.tok_per_sec} tok/s · modo ${msg.metadata.tool_mode || "auto"}`;
    block.appendChild(meta);
  }
  return block;
}

function buildToolTraceDetails(tools) {
  const details = document.createElement("details");
  details.className = "tool-trace";
  const summary = document.createElement("summary");
  summary.textContent = `${tools.length} acción(es) en el workspace`;
  details.appendChild(summary);

  const list = document.createElement("div");
  list.className = "tool-trace-list";
  for (const t of tools) {
    const row = document.createElement("div");
    row.textContent = `${t.ok ? "[OK]" : "[ERROR]"} ${t.summary}`;
    list.appendChild(row);
  }
  details.appendChild(list);
  return details;
}

/* ---------------- Propuestas Diff e Inspector ---------------- */

function buildProposalCard(proposal) {
  state.proposalsById.set(proposal.id, proposal);
  const card = document.createElement("div");
  card.className = "proposal-card";
  card.dataset.proposalId = proposal.id;

  const head = document.createElement("div");
  head.className = "proposal-head";

  const titleGroup = document.createElement("div");
  titleGroup.className = "proposal-title-group";
  const actBadge = document.createElement("span");
  actBadge.className = `badge badge-${proposal.action}`;
  actBadge.textContent = ACTION_LABELS[proposal.action] || proposal.action;
  const pathSpan = document.createElement("span");
  pathSpan.className = "mono-path";
  pathSpan.textContent = proposal.file_path;
  const statsSpan = document.createElement("span");
  statsSpan.className = "diff-stats mono-num";
  statsSpan.innerHTML = `<span class="stat-add">+${proposal.added_lines}</span><span class="stat-del">-${proposal.removed_lines}</span>`;
  titleGroup.append(actBadge, pathSpan, statsSpan);

  const statusBadge = document.createElement("span");
  statusBadge.className = `badge badge-${proposal.status}`;
  statusBadge.dataset.role = "status-badge";
  statusBadge.textContent = STATUS_LABELS[proposal.status] || proposal.status;
  head.append(titleGroup, statusBadge);

  const reasonEl = document.createElement("div");
  reasonEl.className = "proposal-reason";
  reasonEl.textContent = proposal.reason;

  const preview = document.createElement("div");
  preview.className = "diff-preview";
  renderDiffRows(preview, proposal.hunks || [], "unified");

  const footer = document.createElement("div");
  footer.className = "proposal-footer";
  footer.dataset.role = "proposal-footer";
  renderProposalFooter(footer, proposal);

  card.append(head, reasonEl, preview, footer);
  return card;
}

function renderProposalFooter(footer, proposal) {
  footer.textContent = "";
  const inspectBtn = document.createElement("button");
  inspectBtn.type = "button";
  inspectBtn.className = "ghost-btn compact-btn";
  inspectBtn.textContent = "Abrir en inspector";
  inspectBtn.addEventListener("click", () => openDiffInInspector(proposal));

  if (proposal.status === "pending") {
    const fbInput = document.createElement("input");
    fbInput.type = "text";
    fbInput.className = "text-input proposal-feedback-input";
    fbInput.placeholder = "Comentario opcional si rechazas...";

    const actions = document.createElement("div");
    actions.className = "inline-actions";

    const rejectBtn = document.createElement("button");
    rejectBtn.type = "button";
    rejectBtn.className = "ghost-btn compact-btn";
    rejectBtn.textContent = "Rechazar";

    const approveBtn = document.createElement("button");
    approveBtn.type = "button";
    approveBtn.className = "primary-btn compact-btn";
    approveBtn.textContent = "Aprobar y aplicar";

    approveBtn.addEventListener("click", async () => {
      approveBtn.disabled = true;
      rejectBtn.disabled = true;
      await resolveProposal(proposal.id, true, "");
    });
    rejectBtn.addEventListener("click", async () => {
      approveBtn.disabled = true;
      rejectBtn.disabled = true;
      await resolveProposal(proposal.id, false, fbInput.value);
    });

    actions.append(inspectBtn, rejectBtn, approveBtn);
    footer.append(fbInput, actions);
    return;
  }

  const info = document.createElement("span");
  info.className = "muted-meta";
  info.textContent = proposal.feedback ? `Nota: ${proposal.feedback}` : "";
  const actions = document.createElement("div");
  actions.className = "inline-actions";
  actions.appendChild(inspectBtn);

  if (proposal.status === "applied") {
    const revBtn = document.createElement("button");
    revBtn.type = "button";
    revBtn.className = "ghost-btn compact-btn";
    revBtn.textContent = "Revertir";
    revBtn.addEventListener("click", () => revertChangeById(proposal.id));
    actions.appendChild(revBtn);
  }
  footer.append(info, actions);
}

async function resolveProposal(proposalId, approved, feedback) {
  try {
    await apiJson(`/api/proposals/${proposalId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ approved, feedback }),
    });
  } catch (err) {
    alert(`No se pudo resolver la propuesta: ${err.message}`);
  }
}

async function revertChangeById(changeId) {
  try {
    const res = await apiJson(`/api/changes/${changeId}/revert`, { method: "POST" });
    const prop = state.proposalsById.get(changeId);
    if (prop) {
      prop.status = "reverted";
      updateProposalCardUI(changeId, "reverted", "");
    }
    if (state.inspectedDiff?.id === changeId) {
      state.inspectedDiff.status = "reverted";
      renderInspectorDiff();
    }
    await Promise.all([refreshChanges(), refreshFileTree()]);
    if (state.inspectedFile?.path === res.change?.file_path) {
      openFileInInspector(state.inspectedFile.path);
    }
  } catch (err) {
    alert(`Error al revertir: ${err.message}`);
  }
}

function updateProposalCardUI(proposalId, status, feedback) {
  const prop = state.proposalsById.get(proposalId);
  if (prop) {
    prop.status = status;
    if (feedback !== undefined) prop.feedback = feedback;
  }
  const card = document.querySelector(`.proposal-card[data-proposal-id="${proposalId}"]`);
  if (!card || !prop) return;
  const badge = card.querySelector('[data-role="status-badge"]');
  if (badge) {
    badge.className = `badge badge-${status}`;
    badge.textContent = STATUS_LABELS[status] || status;
  }
  const footer = card.querySelector('[data-role="proposal-footer"]');
  if (footer) renderProposalFooter(footer, prop);
}

function openDiffInInspector(item) {
  state.inspectedDiff = item;
  openInspectorTab("diff");
  renderInspectorDiff();
}

function renderInspectorDiff() {
  const item = state.inspectedDiff;
  if (!item) return;
  $("inspector-diff-toolbar").hidden = false;
  $("inspector-diff-path").textContent = item.file_path;
  $("inspector-diff-stats").innerHTML =
    `<span class="stat-add">+${item.added_lines}</span><span class="stat-del">-${item.removed_lines}</span>`;

  $("btn-diff-unified").classList.toggle("is-active", state.diffMode === "unified");
  $("btn-diff-split").classList.toggle("is-active", state.diffMode === "split");

  const actions = $("inspector-diff-actions");
  actions.textContent = "";
  if (item.status === "pending") {
    const rej = document.createElement("button");
    rej.type = "button";
    rej.className = "ghost-btn compact-btn";
    rej.textContent = "Rechazar";
    rej.addEventListener("click", () => resolveProposal(item.id, false, ""));
    const app = document.createElement("button");
    app.type = "button";
    app.className = "primary-btn compact-btn";
    app.textContent = "Aprobar";
    app.addEventListener("click", () => resolveProposal(item.id, true, ""));
    actions.append(rej, app);
  } else if (item.status === "applied") {
    const rev = document.createElement("button");
    rev.type = "button";
    rev.className = "ghost-btn compact-btn";
    rev.textContent = "Revertir";
    rev.addEventListener("click", () => revertChangeById(item.id));
    actions.appendChild(rev);
  } else {
    const st = document.createElement("span");
    st.className = `badge badge-${item.status}`;
    st.textContent = STATUS_LABELS[item.status] || item.status;
    actions.appendChild(st);
  }

  renderDiffRows($("inspector-diff-body"), item.hunks || [], state.diffMode);
}

/* ---------------- Streaming SSE de Chat ---------------- */

async function sendChatMessage() {
  if (state.streaming) return;
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;

  if (!state.activeSessionId) await ensureActiveSession();
  const attached = [...state.attachedFiles];

  input.value = "";
  input.style.height = "auto";
  state.attachedFiles = [];
  renderAttachedChips();

  const chatEl = $("chat-messages");
  if (state.messages.length === 0) chatEl.textContent = "";

  const userMsg = {
    role: "user",
    content: text,
    metadata: attached.length ? { attached_files: attached } : {},
  };
  state.messages.push(userMsg);
  chatEl.appendChild(buildMessageElement(userMsg));

  // Bloque vivo del asistente
  const assistantBlock = document.createElement("div");
  assistantBlock.className = "message-block is-assistant";
  const traceContainer = document.createElement("div");
  const liveBubble = document.createElement("div");
  liveBubble.className = "message-bubble";
  const mdBody = document.createElement("div");
  mdBody.className = "md-body";
  mdBody.textContent = "Procesando con el modelo local...";
  liveBubble.appendChild(mdBody);
  const metaEl = document.createElement("div");
  metaEl.className = "message-meta mono-num";
  assistantBlock.append(traceContainer, liveBubble, metaEl);
  chatEl.appendChild(assistantBlock);
  chatEl.scrollTop = chatEl.scrollHeight;

  state.streaming = true;
  state.abortController = new AbortController();
  $("btn-send").disabled = true;
  $("btn-stop").hidden = false;

  let streamText = "";
  const liveTools = [];

  try {
    const resp = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.activeSessionId,
        message: text,
        attached_files: attached,
      }),
      signal: state.abortController.signal,
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`Error del servidor HTTP ${resp.status}`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";

      for (const frame of frames) {
        const lines = frame.split("\n");
        let dataStr = "";
        for (const ln of lines) {
          if (ln.startsWith(":")) continue;
          if (ln.startsWith("data:")) {
            dataStr += ln.slice(5).trim();
          }
        }
        if (!dataStr) continue;
        let payload;
        try {
          payload = JSON.parse(dataStr);
        } catch (_) {
          continue;
        }
        handleSseEvent(payload);
      }
    }
  } catch (err) {
    if (err.name === "AbortError") {
      metaEl.textContent = "Cancelado por el usuario";
    } else {
      mdBody.textContent = `Error: ${err.message}`;
    }
  } finally {
    state.streaming = false;
    state.activeRunId = null;
    state.abortController = null;
    $("btn-send").disabled = false;
    $("btn-stop").hidden = true;
    await refreshSessions();
  }

  function handleSseEvent(ev) {
    switch (ev.type) {
      case "run_started":
        state.activeRunId = ev.run_id;
        break;
      case "context_stats":
        $("context-budget-label").textContent = `~${ev.estimated_tokens} / ${ev.num_ctx} tok`;
        break;
      case "token":
        streamText += ev.text || "";
        renderSafeMarkdown(mdBody, streamText);
        chatEl.scrollTop = chatEl.scrollHeight;
        break;
      case "stream_clean":
        streamText = ev.content || "";
        if (streamText) {
          renderSafeMarkdown(mdBody, streamText);
        } else {
          mdBody.textContent = "Ejecutando herramientas en el workspace...";
        }
        break;
      case "tool_start":
        metaEl.textContent = `Ejecutando ${ev.name}...`;
        break;
      case "tool_result":
        liveTools.push({ name: ev.name, ok: ev.ok, summary: ev.summary });
        traceContainer.textContent = "";
        traceContainer.appendChild(buildToolTraceDetails(liveTools));
        metaEl.textContent = ev.summary || "";
        break;
      case "proposal": {
        const propCard = buildProposalCard(ev);
        chatEl.insertBefore(propCard, assistantBlock);
        openDiffInInspector(ev);
        chatEl.scrollTop = chatEl.scrollHeight;
        break;
      }
      case "proposal_resolved":
        updateProposalCardUI(ev.id, ev.status, ev.feedback || "");
        if (state.inspectedDiff?.id === ev.id) {
          state.inspectedDiff.status = ev.status;
          renderInspectorDiff();
        }
        refreshChanges();
        if (ev.status === "applied") {
          refreshFileTree();
          if (state.inspectedFile?.path === ev.file_path) {
            openFileInInspector(ev.file_path);
          }
        }
        break;
      case "done": {
        const finalTxt = ev.content || streamText || "(Sin respuesta)";
        renderSafeMarkdown(mdBody, finalTxt);
        metaEl.textContent = `${ev.tokens_generated || 0} tok · ${ev.tok_per_sec || 0} tok/s · modo ${ev.used_tool_mode || "auto"}`;
        state.messages.push({
          role: "assistant",
          content: finalTxt,
          metadata: {
            tokens_generated: ev.tokens_generated,
            tok_per_sec: ev.tok_per_sec,
            tool_mode: ev.used_tool_mode,
            tools: liveTools,
          },
        });
        chatEl.scrollTop = chatEl.scrollHeight;
        break;
      }
      case "error":
        mdBody.textContent = `Aviso: ${ev.message}`;
        metaEl.textContent = "Detenido";
        break;
    }
  }
}

/* ---------------- Diálogos Workspace y Ajustes ---------------- */

async function openWorkspaceDialog() {
  const dlg = $("workspace-dialog");
  const startDir = state.settings?.workspace_path || "";
  $("input-workspace-path").value = startDir;
  await loadBrowseDirectory(startDir);
  dlg.showModal();
}

async function loadBrowseDirectory(dirPath) {
  try {
    const qs = dirPath ? `?dir=${encodeURIComponent(dirPath)}` : "";
    const data = await apiJson(`/api/workspace/browse${qs}`);
    state.browseCurrent = data.current;
    state.browseParent = data.parent;
    $("input-workspace-path").value = data.current;
    $("browse-current-label").textContent = data.current;
    $("btn-browse-up").disabled = !data.parent;

    const drivesEl = $("browse-drives");
    drivesEl.textContent = "";
    for (const d of data.drives || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip-btn";
      btn.textContent = d;
      btn.addEventListener("click", () => loadBrowseDirectory(d));
      drivesEl.appendChild(btn);
    }

    const dirsEl = $("browse-dirs");
    dirsEl.textContent = "";
    for (const sub of data.directories || []) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "browse-dir-item";
      btn.appendChild(createSvgIcon("folder"));
      const sp = document.createElement("span");
      sp.textContent = sub.name;
      btn.appendChild(sp);
      btn.addEventListener("click", () => loadBrowseDirectory(sub.path));
      dirsEl.appendChild(btn);
    }
  } catch (err) {
    $("browse-dirs").textContent = `No se pudo abrir la ruta: ${err.message}`;
  }
}

async function confirmWorkspaceSelection() {
  const chosen = $("input-workspace-path").value.trim() || state.browseCurrent;
  if (!chosen) return;
  try {
    const res = await apiJson("/api/workspace/select", {
      method: "POST",
      body: JSON.stringify({ path: chosen, session_id: state.activeSessionId }),
    });
    state.settings.workspace_path = res.workspace_path;
    state.treeData = res.tree;
    updateTopBarFromSettings();
    renderFileTree();
    $("workspace-dialog").close();
  } catch (err) {
    alert(err.message);
  }
}

function openSettingsDialog() {
  if (!state.settings) return;
  const hw = state.providersInfo?.hardware;
  if (hw) {
    const avxTxt = hw.simd?.avx === false ? "Sin AVX/AVX2 (Modo Legacy compatible)" : "AVX disponible";
    $("hardware-summary-box").textContent =
      `Equipo detectado: ${hw.logical_cores} núcleos lógicos · ${hw.ram_gb ?? "?"} GB RAM · ${avxTxt}`;
  } else {
    $("hardware-summary-box").textContent = "Perfil optimizado para CPU Intel i5 1ra Gen + NVIDIA 1 GB VRAM.";
  }

  renderProfileSelector(state.settings.hardware_profile);
  fillSettingsInputs(state.settings);
  $("settings-dialog").showModal();
}

function renderProfileSelector(selectedKey) {
  const grid = $("profile-selector");
  grid.textContent = "";
  const profiles = state.providersInfo?.hardware_profiles || {};
  for (const [key, prof] of Object.entries(profiles)) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `profile-option${key === selectedKey ? " is-active" : ""}`;
    btn.dataset.profileKey = key;

    const title = document.createElement("span");
    title.className = "profile-option-title";
    title.textContent = prof.short_label;
    const desc = document.createElement("span");
    desc.className = "profile-option-desc";
    desc.textContent = prof.description;
    btn.append(title, desc);

    btn.addEventListener("click", () => {
      renderProfileSelector(key);
      fillSettingsInputs({ ...state.settings, ...prof, hardware_profile: key });
    });
    grid.appendChild(btn);
  }
}

function fillSettingsInputs(cfg) {
  $("set-num-gpu").value = cfg.num_gpu;
  $("set-num-ctx").value = String(cfg.num_ctx);
  $("set-num-thread").value = cfg.num_thread;
  $("set-num-batch").value = cfg.num_batch;
  $("set-max-predict").value = cfg.max_predict_tokens;
  $("set-tool-mode").value = cfg.tool_mode || "auto";
  $("set-temperature").value = cfg.temperature;
  $("set-max-steps").value = cfg.max_steps;
  $("set-ollama-url").value = cfg.ollama_url;
  $("set-llamacpp-url").value = cfg.llamacpp_url;
  $("set-lmstudio-url").value = cfg.lmstudio_url;
}

async function saveSettingsForm(ev) {
  ev.preventDefault();
  const activeProfileBtn = document.querySelector(".profile-option.is-active");
  const hardware_profile = activeProfileBtn?.dataset.profileKey || state.settings.hardware_profile;
  const payload = {
    hardware_profile,
    apply_profile: true,
    num_gpu: Number($("set-num-gpu").value),
    num_ctx: Number($("set-num-ctx").value),
    num_thread: Number($("set-num-thread").value),
    num_batch: Number($("set-num-batch").value),
    max_predict_tokens: Number($("set-max-predict").value),
    tool_mode: $("set-tool-mode").value,
    temperature: Number($("set-temperature").value),
    max_steps: Number($("set-max-steps").value),
    ollama_url: $("set-ollama-url").value.trim(),
    llamacpp_url: $("set-llamacpp-url").value.trim(),
    lmstudio_url: $("set-lmstudio-url").value.trim(),
  };
  try {
    state.settings = await apiJson("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    updateTopBarFromSettings();
    $("settings-dialog").close();
    await refreshProviders();
  } catch (err) {
    alert(`Error guardando ajustes: ${err.message}`);
  }
}

/* ---------------- Navegación de pestañas y eventos ---------------- */

function openLeftTab(tabKey) {
  document.querySelectorAll("[data-left-tab]").forEach((btn) => {
    const active = btn.dataset.leftTab === tabKey;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  ["files", "sessions", "changes"].forEach((k) => {
    $(`tab-${k}`).classList.toggle("is-active", k === tabKey);
  });
}

function openInspectorTab(tabKey) {
  $("inspector-right").classList.remove("is-collapsed");
  document.querySelectorAll("[data-right-tab]").forEach((btn) => {
    const active = btn.dataset.rightTab === tabKey;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  ["diff", "file"].forEach((k) => {
    $(`right-tab-${k}`).classList.toggle("is-active", k === tabKey);
  });
}

function wireEvents() {
  $("btn-toggle-sidebar").addEventListener("click", () => {
    $("sidebar-left").classList.toggle("is-collapsed");
  });
  $("btn-toggle-inspector").addEventListener("click", () => {
    $("inspector-right").classList.toggle("is-collapsed");
  });

  document.querySelectorAll("[data-left-tab]").forEach((btn) => {
    btn.addEventListener("click", () => openLeftTab(btn.dataset.leftTab));
  });
  document.querySelectorAll("[data-right-tab]").forEach((btn) => {
    btn.addEventListener("click", () => openInspectorTab(btn.dataset.rightTab));
  });

  $("btn-theme").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("codigolocal-theme", next);
  });

  $("select-provider").addEventListener("change", async (ev) => {
    const provider = ev.target.value;
    state.settings = await apiJson("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ provider }),
    });
    populateModelSelect();
    updateStatusPill();
  });

  $("select-model").addEventListener("change", async (ev) => {
    const model = ev.target.value;
    state.settings = await apiJson("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ model }),
    });
  });

  $("btn-refresh-providers").addEventListener("click", refreshProviders);
  $("btn-status-pill").addEventListener("click", refreshProviders);
  $("btn-refresh-tree").addEventListener("click", refreshFileTree);
  $("input-file-filter").addEventListener("input", renderFileTree);

  $("btn-new-session").addEventListener("click", async () => {
    const res = await apiJson("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "Nueva sesión" }),
    });
    await refreshSessions();
    await loadSession(res.session.id);
  });

  $("btn-open-workspace").addEventListener("click", openWorkspaceDialog);
  $("btn-close-workspace-dialog").addEventListener("click", () => $("workspace-dialog").close());
  $("btn-cancel-workspace").addEventListener("click", () => $("workspace-dialog").close());
  $("btn-browse-go").addEventListener("click", () => loadBrowseDirectory($("input-workspace-path").value));
  $("btn-browse-up").addEventListener("click", () => {
    if (state.browseParent) loadBrowseDirectory(state.browseParent);
  });
  $("btn-confirm-workspace").addEventListener("click", confirmWorkspaceSelection);

  $("btn-open-settings").addEventListener("click", openSettingsDialog);
  $("btn-context-pill").addEventListener("click", openSettingsDialog);
  $("btn-close-settings-dialog").addEventListener("click", () => $("settings-dialog").close());
  $("btn-cancel-settings").addEventListener("click", () => $("settings-dialog").close());
  $("settings-form").addEventListener("submit", saveSettingsForm);

  document.querySelectorAll("[data-set-gpu]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("set-num-gpu").value = btn.dataset.setGpu;
    });
  });

  $("btn-diff-unified").addEventListener("click", () => {
    state.diffMode = "unified";
    renderInspectorDiff();
  });
  $("btn-diff-split").addEventListener("click", () => {
    state.diffMode = "split";
    renderInspectorDiff();
  });

  $("btn-attach-viewed").addEventListener("click", () => {
    if (state.inspectedFile?.path) attachFile(state.inspectedFile.path);
  });
  $("btn-copy-viewed").addEventListener("click", () => {
    if (state.inspectedFile?.content != null) {
      copyText(state.inspectedFile.content, $("btn-copy-viewed"));
    }
  });

  const chatInput = $("chat-input");
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = `${Math.min(160, chatInput.scrollHeight)}px`;
  });
  chatInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      sendChatMessage();
    }
  });

  $("composer-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    sendChatMessage();
  });

  $("btn-stop").addEventListener("click", async () => {
    if (state.activeRunId) {
      await apiJson(`/api/runs/${state.activeRunId}/cancel`, { method: "POST" }).catch(() => {});
    }
    state.abortController?.abort();
  });
}

async function bootstrap() {
  const savedTheme = localStorage.getItem("codigolocal-theme");
  if (savedTheme === "light" || savedTheme === "dark") {
    document.documentElement.setAttribute("data-theme", savedTheme);
  }
  wireEvents();
  state.settings = await apiJson("/api/settings");
  updateTopBarFromSettings();
  await Promise.all([refreshProviders(), refreshFileTree(), ensureActiveSession()]);
}

bootstrap().catch((err) => {
  console.error("Error inicializando CódigoLocal:", err);
});
