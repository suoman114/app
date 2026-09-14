const sitesTbody = document.getElementById("sites-tbody");
const siteForm = document.getElementById("site-form");
const siteFormStatus = document.getElementById("site-form-status");
const siteFormSubmit = document.getElementById("site-form-submit");
const siteFormCancel = document.getElementById("site-form-cancel");
const settingsForm = document.getElementById("settings-form");
const settingsStatus = document.getElementById("settings-status");
const siteSearchInput = document.getElementById("site-search");
const statusFilterSelect = document.getElementById("status-filter");
const selectAllCheckbox = document.getElementById("select-all-checkbox");
const bulkPullBtn = document.getElementById("bulk-pull-btn");
const bulkPushBtn = document.getElementById("bulk-push-btn");

let allSites = [];
const selectedIds = new Set();

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "요청 실패");
  }
  return data;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

async function loadSettings() {
  try {
    const config = await api("/api/settings/bitbucket");
    settingsForm.base_url.value = config.base_url || "";
    settingsForm.username.value = config.username || "";
    settingsForm.app_password.placeholder = config.app_password_set
      ? "설정됨 (변경하려면 입력)"
      : "App Password 입력";
  } catch (err) {
    settingsStatus.textContent = err.message;
  }
}

settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  settingsStatus.textContent = "저장 중...";
  try {
    await api("/api/settings/bitbucket", {
      method: "PUT",
      body: JSON.stringify({
        base_url: settingsForm.base_url.value.trim(),
        username: settingsForm.username.value.trim(),
        app_password: settingsForm.app_password.value,
      }),
    });
    settingsForm.app_password.value = "";
    settingsStatus.textContent = "저장되었습니다.";
    await loadSettings();
  } catch (err) {
    settingsStatus.textContent = "오류: " + err.message;
  }
});

function resetSiteForm() {
  siteForm.reset();
  siteForm.branch.value = "main";
  siteForm.id.value = "";
  siteFormSubmit.textContent = "추가";
  siteFormCancel.hidden = true;
}

siteFormCancel.addEventListener("click", resetSiteForm);

siteForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = siteForm.id.value;
  const payload = {
    name: siteForm.name.value.trim(),
    repo_url: siteForm.repo_url.value.trim(),
    branch: siteForm.branch.value.trim() || "main",
    description: siteForm.description.value.trim(),
  };
  siteFormStatus.textContent = "저장 중...";
  try {
    if (id) {
      await api(`/api/sites/${id}`, { method: "PUT", body: JSON.stringify(payload) });
      siteFormStatus.textContent = "수정되었습니다.";
    } else {
      await api("/api/sites", { method: "POST", body: JSON.stringify(payload) });
      siteFormStatus.textContent = "추가되었습니다.";
    }
    resetSiteForm();
    await loadSites();
  } catch (err) {
    siteFormStatus.textContent = "오류: " + err.message;
  }
});

function startEdit(site) {
  siteForm.id.value = site.id;
  siteForm.name.value = site.name;
  siteForm.repo_url.value = site.repo_url;
  siteForm.branch.value = site.branch;
  siteForm.description.value = site.description;
  siteFormSubmit.textContent = "수정 저장";
  siteFormCancel.hidden = false;
  siteForm.scrollIntoView({ behavior: "smooth" });
}

function pollProgress(siteId, onUpdate) {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    try {
      const p = await api(`/api/sites/${siteId}/progress`);
      onUpdate(p);
    } catch (err) {
      // ignore transient polling errors, keep trying until stopped
    }
    if (!stopped) setTimeout(tick, 600);
  };
  tick();
  return () => {
    stopped = true;
  };
}

function progressButtonText(action, p) {
  const pct = p.percent != null ? ` ${Math.round(p.percent)}%` : "";
  return `${actionLabel(p.action || action)}${pct}`;
}

async function runAction(site, action, button) {
  const originalLabel = button.textContent;
  const originalTitle = button.title;
  button.disabled = true;
  button.textContent = "시작 중...";
  const stopPolling = pollProgress(site.id, (p) => {
    if (!p.running) return;
    button.textContent = progressButtonText(action, p);
    button.title = p.message || "";
  });
  try {
    let body;
    if (action === "push") {
      const commit_message = window.prompt("커밋 메시지를 입력하세요 (선택)", "") || "";
      body = JSON.stringify({ commit_message });
    }
    const result = await api(`/api/sites/${site.id}/${action}`, { method: "POST", body });
    alert(result.message);
  } catch (err) {
    alert("오류: " + err.message);
  } finally {
    stopPolling();
    button.disabled = false;
    button.textContent = originalLabel;
    button.title = originalTitle;
    await loadSites();
    await loadActivity();
  }
}

async function deleteSite(site) {
  if (!confirm(`"${site.name}" 사이트를 삭제하시겠습니까?`)) return;
  const deleteLocal = site.cloned && confirm("로컬에 clone된 폴더도 함께 삭제할까요?");
  try {
    await api(`/api/sites/${site.id}?delete_local=${deleteLocal}`, { method: "DELETE" });
    await loadSites();
  } catch (err) {
    alert("오류: " + err.message);
  }
}

function statusBadgesHtml(site) {
  if (!site.cloned) {
    return '<span class="badge not-cloned">Not cloned</span>';
  }
  if (site.status_error) {
    return `<span class="badge behind" title="${escapeHtml(site.status_error)}">상태 확인 오류</span>`;
  }
  const badges = [];
  if (site.dirty) badges.push('<span class="badge dirty">변경사항 있음</span>');
  if (site.behind > 0) badges.push(`<span class="badge behind">Pull 필요 (${site.behind})</span>`);
  if (site.ahead > 0) badges.push(`<span class="badge ahead">Push 필요 (${site.ahead})</span>`);
  if (badges.length === 0) badges.push('<span class="badge clean">최신 상태</span>');
  return `<div class="badge-group">${badges.join("")}</div>`;
}

function formatSyncTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
  if (isNaN(d.getTime())) return "-";
  return d.toLocaleString("ko-KR");
}

function siteStatusKey(site) {
  if (!site.cloned) return "not_cloned";
  if (site.dirty) return "dirty";
  if (site.behind > 0) return "behind";
  if (site.ahead > 0) return "ahead";
  return "clean";
}

function matchesSearch(site, query) {
  if (!query) return true;
  const haystack = `${site.name} ${site.repo_url} ${site.description}`.toLowerCase();
  return haystack.includes(query);
}

function getFilteredSites() {
  const query = siteSearchInput.value.trim().toLowerCase();
  const statusFilter = statusFilterSelect.value;
  return allSites.filter((site) => {
    if (!matchesSearch(site, query)) return false;
    if (statusFilter !== "all" && siteStatusKey(site) !== statusFilter) return false;
    return true;
  });
}

function renderFilteredSites() {
  const filtered = getFilteredSites();
  // drop selections for sites that no longer exist (e.g. deleted)
  for (const id of [...selectedIds]) {
    if (!allSites.some((s) => s.id === id)) selectedIds.delete(id);
  }
  renderSites(filtered);
  updateSelectAllState(filtered.filter((s) => s.cloned));
}

function updateSelectAllState(selectableSites) {
  if (selectableSites.length === 0) {
    selectAllCheckbox.checked = false;
    selectAllCheckbox.indeterminate = false;
    return;
  }
  const selectedCount = selectableSites.filter((s) => selectedIds.has(s.id)).length;
  selectAllCheckbox.checked = selectedCount === selectableSites.length;
  selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < selectableSites.length;
}

function renderSites(sites) {
  if (sites.length === 0) {
    sitesTbody.innerHTML = '<tr><td colspan="7" class="empty-row">조건에 맞는 사이트가 없습니다.</td></tr>';
    return;
  }
  sitesTbody.innerHTML = "";
  for (const site of sites) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td></td>
      <td class="name-cell">${escapeHtml(site.name)}</td>
      <td class="url-cell">${escapeHtml(site.repo_url)}</td>
      <td>${escapeHtml(site.branch)}</td>
      <td>${statusBadgesHtml(site)}</td>
      <td class="sync-time">${formatSyncTime(site.last_synced_at)}</td>
      <td class="row-actions"></td>
    `;
    const checkboxCell = tr.querySelector("td");
    const rowCheckbox = document.createElement("input");
    rowCheckbox.type = "checkbox";
    rowCheckbox.disabled = !site.cloned;
    rowCheckbox.checked = selectedIds.has(site.id);
    rowCheckbox.onchange = () => {
      if (rowCheckbox.checked) selectedIds.add(site.id);
      else selectedIds.delete(site.id);
      updateSelectAllState(getFilteredSites().filter((s) => s.cloned));
    };
    checkboxCell.appendChild(rowCheckbox);
    const actionsCell = tr.querySelector(".row-actions");

    const cloneBtn = document.createElement("button");
    cloneBtn.textContent = "Clone";
    cloneBtn.disabled = site.cloned;
    cloneBtn.onclick = () => runAction(site, "clone", cloneBtn);
    actionsCell.appendChild(cloneBtn);

    const pullBtn = document.createElement("button");
    pullBtn.textContent = "Pull";
    pullBtn.disabled = !site.cloned;
    pullBtn.onclick = () => runAction(site, "pull", pullBtn);
    actionsCell.appendChild(pullBtn);

    const pushBtn = document.createElement("button");
    pushBtn.textContent = "Push";
    pushBtn.disabled = !site.cloned;
    pushBtn.onclick = () => runAction(site, "push", pushBtn);
    actionsCell.appendChild(pushBtn);

    const editBtn = document.createElement("button");
    editBtn.textContent = "수정";
    editBtn.onclick = () => startEdit(site);
    actionsCell.appendChild(editBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.textContent = "삭제";
    deleteBtn.className = "danger";
    deleteBtn.onclick = () => deleteSite(site);
    actionsCell.appendChild(deleteBtn);

    sitesTbody.appendChild(tr);
  }
}

async function loadSites() {
  try {
    allSites = await api("/api/sites");
    renderFilteredSites();
  } catch (err) {
    sitesTbody.innerHTML = `<tr><td colspan="7" class="empty-row">오류: ${escapeHtml(err.message)}</td></tr>`;
  }
}

siteSearchInput.addEventListener("input", renderFilteredSites);
statusFilterSelect.addEventListener("change", renderFilteredSites);

selectAllCheckbox.addEventListener("change", () => {
  const selectable = getFilteredSites().filter((s) => s.cloned);
  if (selectAllCheckbox.checked) {
    for (const site of selectable) selectedIds.add(site.id);
  } else {
    for (const site of selectable) selectedIds.delete(site.id);
  }
  renderFilteredSites();
});

function getSelectedSites() {
  return allSites.filter((s) => selectedIds.has(s.id));
}

async function runBulkAction(action, button, { commitMessage } = {}) {
  const targets = getSelectedSites().filter((s) => s.cloned);
  if (targets.length === 0) {
    alert("선택된(clone된) 사이트가 없습니다.");
    return;
  }
  const originalLabel = button.textContent;
  button.disabled = true;
  const results = [];
  for (let i = 0; i < targets.length; i++) {
    const site = targets[i];
    const prefix = `(${i + 1}/${targets.length}) ${site.name}: `;
    button.textContent = prefix + "시작 중...";
    const stopPolling = pollProgress(site.id, (p) => {
      if (!p.running) return;
      button.textContent = prefix + progressButtonText(action, p);
      button.title = p.message || "";
    });
    try {
      const body = action === "push" ? JSON.stringify({ commit_message: commitMessage || "" }) : undefined;
      const result = await api(`/api/sites/${site.id}/${action}`, { method: "POST", body });
      results.push({ site, ok: result.ok, message: result.message });
    } catch (err) {
      results.push({ site, ok: false, message: err.message });
    } finally {
      stopPolling();
    }
  }
  button.disabled = false;
  button.textContent = originalLabel;
  button.title = "";
  const failed = results.filter((r) => !r.ok);
  const summary =
    `${results.length}개 중 ${results.length - failed.length}개 성공` +
    (failed.length ? `, ${failed.length}개 실패:\n` + failed.map((r) => `- ${r.site.name}: ${r.message}`).join("\n") : "");
  alert(summary);
  await loadSites();
  await loadActivity();
}

bulkPullBtn.addEventListener("click", () => runBulkAction("pull", bulkPullBtn));

bulkPushBtn.addEventListener("click", () => {
  const targets = getSelectedSites().filter((s) => s.cloned);
  if (targets.length === 0) {
    alert("선택된(clone된) 사이트가 없습니다.");
    return;
  }
  const commitMessage = window.prompt(
    `선택된 ${targets.length}개 사이트에 공통으로 사용할 커밋 메시지를 입력하세요 (선택)`,
    ""
  );
  if (commitMessage === null) return; // cancelled
  runBulkAction("push", bulkPushBtn, { commitMessage });
});

const activityTbody = document.getElementById("activity-tbody");

function actionLabel(action) {
  return { clone: "Clone", pull: "Pull", push: "Push" }[action] || action;
}

async function loadActivity() {
  try {
    const logs = await api("/api/activity?limit=50");
    if (logs.length === 0) {
      activityTbody.innerHTML = '<tr><td colspan="5" class="empty-row">아직 작업 이력이 없습니다.</td></tr>';
      return;
    }
    activityTbody.innerHTML = logs
      .map(
        (log) => `
      <tr>
        <td class="sync-time">${formatSyncTime(log.created_at)}</td>
        <td>${escapeHtml(log.site_name)}</td>
        <td>${actionLabel(log.action)}</td>
        <td><span class="badge ${log.ok ? "clean" : "behind"}">${log.ok ? "성공" : "실패"}</span></td>
        <td>${escapeHtml(log.message)}</td>
      </tr>`
      )
      .join("");
  } catch (err) {
    activityTbody.innerHTML = `<tr><td colspan="5" class="empty-row">오류: ${escapeHtml(err.message)}</td></tr>`;
  }
}

loadSettings();
loadSites();
loadActivity();
