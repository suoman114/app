const sitesTbody = document.getElementById("sites-tbody");
const siteForm = document.getElementById("site-form");
const siteFormStatus = document.getElementById("site-form-status");
const siteFormSubmit = document.getElementById("site-form-submit");
const siteFormCancel = document.getElementById("site-form-cancel");
const settingsForm = document.getElementById("settings-form");
const settingsStatus = document.getElementById("settings-status");

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

async function runAction(site, action, button) {
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "처리 중...";
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
    button.disabled = false;
    button.textContent = originalLabel;
    await loadSites();
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

function renderSites(sites) {
  if (sites.length === 0) {
    sitesTbody.innerHTML = '<tr><td colspan="6" class="empty-row">등록된 사이트가 없습니다.</td></tr>';
    return;
  }
  sitesTbody.innerHTML = "";
  for (const site of sites) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(site.name)}</td>
      <td>${escapeHtml(site.repo_url)}</td>
      <td>${escapeHtml(site.branch)}</td>
      <td>${statusBadgesHtml(site)}</td>
      <td class="sync-time">${formatSyncTime(site.last_synced_at)}</td>
      <td class="row-actions"></td>
    `;
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
    const sites = await api("/api/sites");
    renderSites(sites);
  } catch (err) {
    sitesTbody.innerHTML = `<tr><td colspan="6" class="empty-row">오류: ${escapeHtml(err.message)}</td></tr>`;
  }
}

loadSettings();
loadSites();
