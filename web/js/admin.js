import { api, esc, capital } from "./api.js";

const $ = (id) => document.getElementById(id);
let noticeFn = () => {};
let authenticated = false;
let clientsCache = [];
let incidentsCache = [];

function showLogin(show) {
  $("admin-login-panel").hidden = !show;
  $("admin-workspace").hidden = show;
  $("admin-refresh").hidden = show;
}

function metric(label, value, note, kind = "") {
  return `<article class="sheet admin-metric ${kind}"><p>${esc(label)}</p><strong>${esc(value)}</strong><span>${esc(note)}</span></article>`;
}

function renderMetrics(data) {
  $("admin-metrics").innerHTML = [
    metric("Active clients", `${data.active_clients ?? 0}`, `${data.clients ?? 0} registered`, "metric-blue"),
    metric("Datasets", `${data.datasets ?? 0}`, "Configured monitoring sources"),
    metric("Open incidents", `${data.open_incidents ?? 0}`, `${data.incidents ?? 0} recorded total`, (data.open_incidents ?? 0) ? "metric-red" : ""),
    metric("Recommendations", `${data.recommendations ?? 0}`, "Saved for review", "metric-purple"),
  ].join("");
  const service = data.service || {};
  $("admin-service-status").innerHTML = `
    <div class="service-row"><span>API process</span><strong class="service-good"><i></i>${esc(capital(service.status || "unknown"))}</strong></div>
    <div class="service-row"><span>Core engine</span><strong>${esc(service.engine || "Invariant Sentinel")}</strong></div>
    <div class="service-row"><span>Metadata storage</span><strong>${esc(service.storage || "SQLite")}</strong></div>
    <div class="service-row"><span>Runs this session</span><strong>${esc(data.runs_this_session ?? 0)}</strong></div>
    <p class="admin-footnote">Monitoring run progress is currently held in memory and resets on server restart. Client, incident, recommendation, and audit records are persisted locally.</p>`;
  const audit = data.audit || [];
  $("admin-audit").innerHTML = audit.length ? audit.map((a) => `
    <div class="audit-row"><span class="audit-dot"></span><div><strong>${esc(a.action.replaceAll("_", " "))}</strong><p>${esc(a.created_at)} · ${esc(a.actor)}</p></div></div>`).join("") : `<p class="empty-panel">Admin actions will appear here.</p>`;
}

function renderClients(clients) {
  clientsCache = clients;
  $("client-count").textContent = `${clients.length} client${clients.length === 1 ? "" : "s"}`;
  $("admin-client-rows").innerHTML = clients.length ? clients.map((c) => `
    <tr><td><strong>${esc(c.name)}</strong><div class="muted small">${esc(c.contact_email || "No contact email")}</div>${c.notes ? `<div class="muted small">${esc(c.notes)}</div>` : ""}</td>
    <td><span class="admin-status ${c.status === "active" ? "is-active" : "is-paused"}">${esc(capital(c.status))}</span></td>
    <td class="num">${esc(c.incident_count ?? 0)}</td><td><button class="link" data-client-toggle="${c.id}" type="button">${c.status === "active" ? "Pause" : "Activate"}</button></td></tr>`).join("") : `<tr><td colspan="4" class="empty-panel">No clients yet. Add your first client above.</td></tr>`;
}

function renderRecommendation(rec) {
  if (!rec?.payload) return "";
  const r = rec.payload;
  return `<div class="recommendation-card"><div class="recommendation-top"><span class="recommendation-label">REMEDIATION SUGGESTION</span><span class="admin-status is-review">${esc((rec.status || r.status || "pending_review").replaceAll("_", " "))}</span></div>
    <h3>${esc(r.title)}</h3><p class="recommendation-why">${esc(r.reasoning)}</p>
    <div class="recommendation-evidence"><strong>Evidence considered</strong><ul>${(r.evidence || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    <div class="recommendation-columns"><div><strong>Recommended steps</strong><ol>${(r.action_steps || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ol></div><div><strong>How to validate</strong><ul>${(r.validation_criteria || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
    <p class="admin-footnote">Confidence: ${esc(r.confidence || "not rated")}. ${(r.limitations || []).map(esc).join(" ")}</p></div>`;
}

function renderIncidents(incidents) {
  incidentsCache = incidents;
  $("admin-incident-list").innerHTML = incidents.length ? incidents.map((i) => {
    const suspect = i.suspect || (i.evidence?.candidates?.[0]?.label || i.evidence?.candidates?.[0]?.feature || "Not isolated");
    const abnormal = i.verdict !== "normal" && i.verdict !== "shift";
    return `<article class="admin-incident" data-incident="${i.id}">
      <div class="incident-main"><div class="incident-meta"><span class="verdict-pill verdict-${esc(i.verdict)}">${esc(i.verdict)}</span><span class="muted small">${esc(i.dataset)} · run ${esc(i.run_id)} · batch ${esc((i.batch_index ?? 0) + 1)}</span></div>
        <h3>${esc(i.title || "Drift incident")}</h3><p>${esc(i.headline || "No summary available.")}</p>
        <div class="incident-facts"><span><b>Suspected feature</b>${esc(suspect)}</span><span><b>Confidence</b>${esc(i.confidence || "–")}</span><span><b>Created</b>${esc(i.created_at)}</span></div>
        ${renderRecommendation(i.recommendation)}
      </div><div class="incident-actions"><label class="small muted" for="incident-status-${i.id}">Workflow status</label><select id="incident-status-${i.id}" data-incident-status="${i.id}"><option value="open" ${i.status === "open" ? "selected" : ""}>Open</option><option value="in_review" ${i.status === "in_review" ? "selected" : ""}>In review</option><option value="resolved" ${i.status === "resolved" ? "selected" : ""}>Resolved</option><option value="dismissed" ${i.status === "dismissed" ? "selected" : ""}>Dismissed</option></select>
        <label class="small muted" for="incident-client-${i.id}">Client assignment</label><select id="incident-client-${i.id}" data-incident-client="${i.id}"><option value="">Unassigned</option>${clientsCache.map((c) => `<option value="${c.id}" ${Number(i.client_id) === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>
        ${i.recommendation ? `<button class="btn quiet" data-recommend="${i.id}" type="button">Regenerate suggestion</button>` : `<button class="btn" data-recommend="${i.id}" type="button">Recommend remediation</button>`}</div>
      </article>`;
  }).join("") : `<div class="admin-empty"><div class="empty-symbol">✓</div><h3>No incidents in this view</h3><p>When Sentinel detects a quality issue, broken relationship, ambiguous diagnosis, or insufficient data, it will appear here.</p></div>`;
}

async function refreshDashboard() {
  const [overview, clients, incidents] = await Promise.all([
    api("/admin/overview"), api("/admin/clients"), api(`/admin/incidents?status=${encodeURIComponent($("incident-filter").value)}`),
  ]);
  renderMetrics(overview);
  renderClients(clients);
  renderIncidents(incidents);
}

export async function loadAdmin() {
  const me = await api("/admin/me");
  authenticated = Boolean(me.authenticated);
  showLogin(!authenticated);
  if (authenticated) await refreshDashboard();
}

export function initAdmin({ notice }) {
  noticeFn = notice || (() => {});
  $("admin-login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("admin-login-error"); err.hidden = true;
    const button = e.currentTarget.querySelector("button[type=submit]"); button.disabled = true;
    try {
      await api("/admin/login", { method: "POST", body: { password: $("admin-password").value } });
      $("admin-password").value = "";
      authenticated = true;
      showLogin(false);
      await refreshDashboard();
    } catch (error) {
      err.textContent = error.message; err.hidden = false;
    } finally { button.disabled = false; }
  });

  $("admin-logout").addEventListener("click", async () => {
    try { await api("/admin/logout", { method: "POST" }); } finally { authenticated = false; showLogin(true); }
  });
  $("admin-refresh").addEventListener("click", async () => {
    try { await refreshDashboard(); noticeFn("Admin dashboard refreshed."); } catch (e) { noticeFn(e.message, true); }
  });
  $("incident-filter").addEventListener("change", async () => {
    try { renderIncidents(await api(`/admin/incidents?status=${encodeURIComponent($("incident-filter").value)}`)); }
    catch (e) { noticeFn(e.message, true); }
  });
  $("client-create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = e.currentTarget.querySelector("button[type=submit]"); button.disabled = true;
    try {
      await api("/admin/clients", { method: "POST", body: { name: $("client-name").value, contact_email: $("client-email").value, notes: $("client-notes").value, status: "active" } });
      e.currentTarget.reset(); await refreshDashboard(); noticeFn("Client added.");
    } catch (error) { noticeFn(error.message, true); }
    finally { button.disabled = false; }
  });

  document.addEventListener("click", async (e) => {
    const toggle = e.target.closest("[data-client-toggle]");
    if (toggle) {
      const c = clientsCache.find((x) => x.id === Number(toggle.dataset.clientToggle));
      if (!c) return;
      toggle.disabled = true;
      try { await api(`/admin/clients/${c.id}`, { method: "PATCH", body: { status: c.status === "active" ? "paused" : "active" } }); await refreshDashboard(); }
      catch (error) { noticeFn(error.message, true); }
      finally { toggle.disabled = false; }
      return;
    }
    const recommend = e.target.closest("[data-recommend]");
    if (recommend) {
      const id = Number(recommend.dataset.recommend); recommend.disabled = true; recommend.textContent = "Preparing…";
      try {
        await api(`/admin/incidents/${id}/recommendation`, { method: "POST", body: {} });
        await refreshDashboard();
        document.querySelector(`[data-incident="${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (error) { noticeFn(error.message, true); }
      finally { recommend.disabled = false; }
      return;
    }
  });
  document.addEventListener("change", async (e) => {
    const clientSelect = e.target.closest("[data-incident-client]");
    if (clientSelect) {
      clientSelect.disabled = true;
      try { await api(`/admin/incidents/${clientSelect.dataset.incidentClient}/client`, { method: "PATCH", body: { client_id: clientSelect.value ? Number(clientSelect.value) : null } }); await refreshDashboard(); }
      catch (error) { noticeFn(error.message, true); }
      finally { clientSelect.disabled = false; }
      return;
    }
    const select = e.target.closest("[data-incident-status]");
    if (!select) return;
    select.disabled = true;
    try { await api(`/admin/incidents/${select.dataset.incidentStatus}/status`, { method: "PATCH", body: { status: select.value } }); await refreshDashboard(); }
    catch (error) { noticeFn(error.message, true); }
    finally { select.disabled = false; }
  });
}
