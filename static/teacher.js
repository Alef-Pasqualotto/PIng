const state = {
  classes: [],
  selectedClass: null,
  activeSession: null,
  rosterTimer: null,
  network: null,
  kbd: { active: false, context: null, index: 0 },
};
const $ = (selector) => document.querySelector(selector);

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data =
    response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(data.detail || "Não foi possível concluir a operação.");
  return data;
}

function toast(text, error = false) {
  const el = $("#toast");
  el.textContent = text;
  el.style.background = error ? "#b42318" : "#17202d";
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3200);
}

function esc(value) {
  const el = document.createElement("span");
  el.textContent = value ?? "";
  return el.innerHTML;
}
function currentClass() {
  return state.classes.find((item) => item.id === Number(state.selectedClass));
}

async function loadClasses(keepSelection = true) {
  const previous = keepSelection ? Number(state.selectedClass) : null;
  state.classes = await api("/classes");
  state.selectedClass = state.classes.some((c) => c.id === previous)
    ? previous
    : state.classes[0]?.id || null;
  for (const selector of [
    "#class-picker",
    "#enrollment-class",
    "#history-class",
  ]) {
    const el = $(selector);
    el.innerHTML = state.classes.length
      ? state.classes
          .map((c) => `<option value="${c.id}">${esc(c.name)}</option>`)
          .join("")
      : '<option value="">Nenhuma turma</option>';
    if (state.selectedClass) el.value = state.selectedClass;
  }
  await refreshSession();
}

async function refreshSession() {
  clearInterval(state.rosterTimer);
  state.rosterTimer = null;
  state.activeSession = null;
  const cls = currentClass();
  $("#delete-class").disabled = !cls;
  $("#session-button").disabled = !cls;
  if (!cls) {
    $("#session-title").textContent = "Nenhuma turma selecionada";
    $("#session-description").textContent = "Crie uma turma para iniciar.";
    renderRoster([]);
    return;
  }
  $("#session-title").textContent = cls.name;
  const status = await api(`/session/status?class_id=${cls.id}`);
  state.activeSession = status.is_open ? status.session_id : null;
  $("#session-description").textContent = status.is_open
    ? "A chamada está aberta e recebendo confirmações."
    : "Nenhuma chamada aberta para esta turma.";
  $("#session-button").textContent = status.is_open
    ? "Encerrar chamada"
    : "Abrir chamada";
  $("#session-button").className = status.is_open ? "secondary" : "primary";
  if (state.activeSession) {
    await loadRoster();
    state.rosterTimer = setInterval(loadRoster, 3000);
  } else renderRoster([]);
}

async function loadRoster() {
  if (!state.activeSession) return;
  try {
    renderRoster(await api(`/session/${state.activeSession}/roster`));
  } catch (error) {
    toast(error.message, true);
  }
}

function renderRoster(rows) {
  state._rosterRows = rows;
  $("#present-count").textContent = rows.filter((r) => r.present).length;
  $("#absent-count").textContent = rows.filter((r) => !r.present).length;
  $("#roster-empty").style.display = rows.length ? "none" : "block";
  $("#roster-empty").textContent = state.activeSession
    ? "Nenhum estudante matriculado nesta turma."
    : "Abra uma chamada para acompanhar as presenças.";
  $("#kbd-mode-roster").disabled = !rows.length;
  $("#roster-list").innerHTML = rows
    .map(
      (r) =>
        `<div class="table-row roster-row" data-attendance-id="${r.attendance_id}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" data-student-id="${r.student_id}"><div><div class="student-name">${esc(r.student_name || "Nome não informado")}</div><div class="small">${esc(r.device_id)}</div></div><span class="badge ${r.present ? "success" : "warning"}">${r.present ? "Presente" : "Ausente"}</span><div class="row-actions"><button class="mini present" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" data-attendance-student="${r.student_id}" data-present="true">Presente</button><button class="mini absent" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" data-attendance-student="${r.student_id}" data-present="false">Ausente</button></div></div>`,
    )
    .join("");
  if (state.kbd.active && state.kbd.context === "roster")
    highlightKbdRow("roster");
}

async function setAttendance(studentId, device_id, class_id, present) {
  console.log({ device_id, class_id, present });
  await api(
    `/session/${state.activeSession}/students/${studentId}/attendance`,
    { method: "PUT", body: JSON.stringify({ device_id, class_id, present }) },
  );
  await loadRoster();
}

async function loadStudents() {
  const [students, allClasses] = await Promise.all([
    api("/students"),
    api("/classes"),
  ]);
  const classId = Number($("#enrollment-class").value);
  const enrolled = classId ? await api(`/classes/${classId}/students`) : [];
  const enrolledIds = new Set(enrolled.map((s) => s.id));

  // Per-student enrollments (for the expanded row)
  const studentEnrollments = {};
  await Promise.all(
    allClasses.map(async (c) => {
      const members = await api(`/classes/${c.id}/students`);
      members.forEach((s) => {
        if (!studentEnrollments[s.id]) studentEnrollments[s.id] = [];
        studentEnrollments[s.id].push(c.name);
      });
    }),
  );

  state._students = students.map((s) => ({
    ...s,
    enrollments: studentEnrollments[s.id] || [],
  }));
  state._enrolledIds = enrolledIds;
  renderStudents();
}

function renderStudents() {
  const query = ($("#student-search").value || "").toLowerCase();
  const students = (state._students || []).filter(
    (s) =>
      !query ||
      (s.name || "").toLowerCase().includes(query) ||
      (s.device_id || "").toLowerCase().includes(query),
  );
  const enrolledIds = state._enrolledIds || new Set();

  $("#students-list").innerHTML = students.length
    ? students
        .map((s) => {
          const classesHtml = s.enrollments.length
            ? s.enrollments
                .map((n) => `<span class="badge neutral">${esc(n)}</span>`)
                .join(" ")
            : '<span class="muted">Nenhuma turma</span>';
          return `
      <div class="table-row student-row" data-student-id="${s.id}">
        <div>
          <div class="student-name">${esc(s.name || "Nome não informado")}</div>
          <div class="small">${esc(s.device_id)}</div>
        </div>
        <button class="mini" data-edit-student="${s.id}" data-name="${esc(s.name || "")}">Editar nome</button>
        <div class="row-actions">
          <button class="mini" data-device-student="${s.id}" data-device="${esc(s.device_id)}">Trocar device</button>
          <button class="mini ${enrolledIds.has(s.id) ? "absent" : "present"}" data-enroll-student="${s.id}" data-enrolled="${enrolledIds.has(s.id)}">${enrolledIds.has(s.id) ? "Remover da turma" : "Matricular"}</button>
        </div>
      </div>
      <div class="student-expand" id="expand-${s.id}" hidden>
        <p class="eyebrow" style="margin:0 0 8px">TURMAS MATRICULADO</p>
        <div class="expand-classes">${classesHtml}</div>
      </div>`;
        })
        .join("")
    : '<div class="empty">Nenhum estudante encontrado.</div>';
}

async function loadHistory() {
  const classId = Number($("#history-class").value);
  if (!classId) {
    $("#history-list").innerHTML =
      '<div class="empty">Crie uma turma para ver o histórico.</div>';
    return;
  }
  const sessions = await api(`/classes/${classId}/sessions`);
  $("#history-list").innerHTML = sessions.length
    ? sessions
        .map(
          (s) =>
            `<div class="table-row"><div><div class="student-name">Chamada de ${esc(s.date)}</div><div class="small">Sessão #${s.id}</div></div><span class="badge ${s.is_open ? "success" : "neutral"}">${s.is_open ? "Aberta" : "Encerrada"}</span><div class="row-actions"><button class="mini" data-review-session="${s.id}" data-review-date="${esc(s.date)}">Ver lista</button><button class="mini" data-export-session="${s.id}">Exportar CSV</button></div></div>`,
        )
        .join("")
    : '<div class="empty">Nenhuma chamada registrada para esta turma.</div>';
}

async function reviewSession(id, date) {
  const rows = await api(`/session/${id}/roster`);
  state._historySessionId = id;
  state._historyRows = rows;
  const card = $("#history-roster-card");
  card.hidden = false;
  $("#history-roster-title").textContent = `Chamada de ${date}`;
  $("#history-present-count").textContent = rows.filter(
    (r) => r.present,
  ).length;
  $("#history-absent-count").textContent = rows.filter(
    (r) => !r.present,
  ).length;
  $("#history-roster-list").innerHTML = rows.length
    ? rows
        .map(
          (r) =>
            `<div class="table-row roster-row" data-attendance-id="${r.attendance_id}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" data-student-id="${r.student_id}"><div><div class="student-name">${esc(r.student_name || "Nome não informado")}</div><div class="small">${esc(r.device_id)}</div></div><span class="badge ${r.present ? "success" : "warning"}">${r.present ? "Presente" : "Ausente"}</span><div class="row-actions"><button data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" class="mini present" data-history-attendance="${r.attendance_id}" data-present="true">Presente</button><button data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" class="mini absent" data-history-attendance="${r.attendance_id}" data-present="false">Ausente</button></div></div>`,
        )
        .join("")
    : '<div class="empty">Nenhum estudante nesta chamada.</div>';
  card.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// Keyboard attendance mode
// ---------------------------------------------------------------------------

function kbdRows(context) {
  const listId = context === "roster" ? "#roster-list" : "#history-roster-list";
  return Array.from(document.querySelectorAll(`${listId} .roster-row`));
}

function highlightKbdRow(context) {
  const rows = kbdRows(context);
  rows.forEach((r, i) =>
    r.classList.toggle("kbd-focus", i === state.kbd.index),
  );
  const focused = rows[state.kbd.index];
  if (focused) focused.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function enterKeyboardMode(context) {
  state.kbd.active = true;
  state.kbd.context = context;
  state.kbd.index = 0;
  const btn = context === "roster" ? "#kbd-mode-roster" : "#kbd-mode-history";
  const hint = context === "roster" ? "#kbd-hint-roster" : "#kbd-hint-history";
  $(btn).textContent = "✕ Sair da chamada rápida";
  $(btn).classList.add("kbd-active");
  $(hint).hidden = false;
  highlightKbdRow(context);
  toast(
    "Chamada rápida ativa. Enter = presente, Backspace = ausente, Tab = pular.",
  );
}

function exitKeyboardMode() {
  const context = state.kbd.context;
  state.kbd.active = false;
  state.kbd.context = null;
  state.kbd.index = 0;
  kbdRows(context).forEach((r) => r.classList.remove("kbd-focus"));
  const btn = context === "roster" ? "#kbd-mode-roster" : "#kbd-mode-history";
  const hint = context === "roster" ? "#kbd-hint-roster" : "#kbd-hint-history";
  $(btn).textContent = "⌨ Chamada rápida";
  $(btn).classList.remove("kbd-active");
  $(hint).hidden = true;
}

async function kbdSetAttendance(context, present) {
  const rows = kbdRows(context);
  const row = rows[state.kbd.index];
  device_id = row.getAttribute("data-device-id");
  class_id = row.getAttribute("data-class-id");
  if (!row) return;
  if (row.dataset.attendanceId != "null") {
    attendanceId = row.dataset.attendanceId;
  } else {
    attendanceId = -1;
  }
  try {
    await api(`/attendance/${attendanceId}`, {
      method: "PATCH",
      body: JSON.stringify({ device_id, class_id, present }),
    });
    // Update badge inline without a full reload
    const badge = row.querySelector(".badge");
    badge.className = `badge ${present ? "success" : "warning"}`;
    badge.textContent = present ? "Presente" : "Ausente";
    // Advance to next
    kbdAdvance(context);
  } catch (e) {
    toast(e.message, true);
  }
}

function kbdAdvance(context) {
  const rows = kbdRows(context);
  if (state.kbd.index >= rows.length - 1) {
    exitKeyboardMode();
    toast("Chamada rápida concluída.");
  } else {
    state.kbd.index++;
    highlightKbdRow(context);
  }
}

document.addEventListener("keydown", async (e) => {
  if (!state.kbd.active) return;
  if (["Enter", "Backspace", "Tab"].includes(e.key)) e.preventDefault();
  if (e.key === "Enter") await kbdSetAttendance(state.kbd.context, true);
  if (e.key === "Backspace") await kbdSetAttendance(state.kbd.context, false);
  if (e.key === "Tab") kbdAdvance(state.kbd.context);
});

async function exportSession(id) {
  if (window.pywebview?.api?.save_csv) {
    const result = await window.pywebview.api.save_csv(id);
    if (result) toast("Arquivo CSV salvo.");
  } else window.location.href = `/session/${id}/export`;
}

async function loadNetwork() {
  const [network, logInfo] = await Promise.all([
    api("/api/network/status"),
    api("/api/debug/log-info"),
  ]);
  state.network = network;
  state.logInfo = logInfo;
  $("#student-url").textContent = state.network.student_url;
  $("#network-url-detail").textContent = state.network.student_url;
  $("#network-qr").src = `/api/network/qr?t=${Date.now()}`;
  $("#ssid").value = state.network.ssid;
  $("#password").value = state.network.password;
  $("#network-badge").className =
    `badge ${state.network.started ? "success" : "neutral"}`;
  $("#network-badge").textContent = state.network.started
    ? "Hotspot ativo"
    : "Rede existente";
  $("#network-hint").textContent = state.network.started
    ? `Conecte os celulares à rede “${state.network.ssid}” e abra o endereço.`
    : "Conecte computador e celulares à mesma rede e abra este endereço.";
  $("#compatibility").className =
    `status ${state.network.compatibility.supported ? "success" : "warning"}`;
  $("#compatibility").textContent = state.network.compatibility.detail;
  $("#toggle-network").textContent = state.network.started
    ? "Parar hotspot"
    : "Iniciar hotspot";
  $("#toggle-network").disabled =
    !state.network.started && !state.network.compatibility.supported;
  $("#windows-hotspot").style.display = state.network.compatibility.supported
    ? "none"
    : "inline-block";
  $("#log-path").textContent = logInfo.path;
}

function showView(name) {
  document
    .querySelectorAll(".view")
    .forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  document
    .querySelectorAll(".nav-item")
    .forEach((v) => v.classList.toggle("active", v.dataset.view === name));
  $("#view-title").textContent = {
    dashboard: "Visão geral",
    students: "Estudantes",
    history: "Histórico",
    network: "Rede da sala",
  }[name];
  if (name === "students") loadStudents().catch((e) => toast(e.message, true));
  if (name === "history") loadHistory().catch((e) => toast(e.message, true));
  if (name === "network") loadNetwork().catch((e) => toast(e.message, true));
}

function promptModal(title, text, value = "") {
  const dialog = $("#modal");
  $("#modal-title").textContent = title;
  $("#modal-text").textContent = text;
  $("#modal-input").value = value;
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () =>
        resolve(
          dialog.returnValue === "default"
            ? $("#modal-input").value.trim()
            : null,
        ),
      { once: true },
    );
  });
}

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) return showView(nav.dataset.view);
  const attendance = event.target.closest("[data-attendance-student]");
  
  if(attendance)
    return setAttendance(
      Number(attendance.dataset.attendanceStudent),
      attendance.getAttribute("data-device-id"),
      attendance.getAttribute("data-class-id"),
      attendance.dataset.present === "true",
    ).catch((e) => toast(e.message, true));
  const edit = event.target.closest("[data-edit-student]");
  if (edit) {
    const name = await promptModal(
      "Editar estudante",
      "Informe o nome que aparecerá nas listas.",
      edit.dataset.name,
    );
    if (name) {
      await api(`/students/${edit.dataset.editStudent}/name`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      await loadStudents();
    }
    return;
  }
  const deviceBtn = event.target.closest("[data-device-student]");
  if (deviceBtn) {
    const newDevice = await promptModal(
      "Trocar device ID",
      "Cole o novo device ID do estudante (ex: após troca de celular).",
      deviceBtn.dataset.device,
    );
    if (newDevice) {
      await api(`/students/${deviceBtn.dataset.deviceStudent}/device`, {
        method: "PATCH",
        body: JSON.stringify({ device_id: newDevice }),
      });
      await loadStudents();
      toast("Device ID atualizado.");
    }
    return;
  }
  const row = event.target.closest(".student-row");
  if (row && !event.target.closest("button")) {
    const id = row.dataset.studentId;
    const expand = $(`#expand-${id}`);
    expand.hidden = !expand.hidden;
    row.classList.toggle("expanded", !expand.hidden);
    return;
  }
  const enroll = event.target.closest("[data-enroll-student]");
  if (enroll) {
    const body = JSON.stringify({
      class_id: Number($("#enrollment-class").value),
      student_id: Number(enroll.dataset.enrollStudent),
    });
    await api("/enrollments", {
      method: enroll.dataset.enrolled === "true" ? "DELETE" : "POST",
      body,
    });
    await loadStudents();
    return;
  }
  const review = event.target.closest("[data-review-session]");
  if (review)
    return reviewSession(
      review.dataset.reviewSession,
      review.dataset.reviewDate,
    ).catch((e) => toast(e.message, true));
  const histAtt = event.target.closest("[data-history-attendance]");
  if (histAtt) {
    device_id = histAtt.getAttribute("data-device-id"),
    class_id = histAtt.getAttribute("data-class-id"),
    await api(`/attendance/${histAtt.dataset.historyAttendance}`, {
      method: "PATCH",
      body: JSON.stringify({ device_id: device_id, class_id: class_id, present: histAtt.dataset.present === "true" }),
    });
    await reviewSession(
      state._historySessionId,
      $("#history-roster-title").textContent.replace("Chamada de ", ""),
    );
    return;
  }
  const exp = event.target.closest("[data-export-session]");
  if (exp) return exportSession(exp.dataset.exportSession);
});

$("#class-picker").addEventListener("change", async (e) => {
  state.selectedClass = Number(e.target.value);
  document
    .querySelectorAll("#enrollment-class,#history-class")
    .forEach((x) => (x.value = state.selectedClass));
  await refreshSession();
});
$("#add-class").addEventListener("click", async () => {
  const name = await promptModal(
    "Criar turma",
    "Informe um nome curto, como “3º A - Matemática”.",
  );
  if (name) {
    const c = await api("/classes", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    state.selectedClass = c.id;
    await loadClasses();
    toast("Turma criada.");
  }
});
$("#delete-class").addEventListener("click", async () => {
  const cls = currentClass();
  if (
    !cls ||
    !confirm(
      `Excluir a turma “${cls.name}”? Esta ação só é permitida quando não há registros vinculados.`,
    )
  )
    return;
  try {
    await api(`/classes/${cls.id}`, { method: "DELETE" });
    await loadClasses(false);
    toast("Turma excluída.");
  } catch (e) {
    toast(
      "A turma possui estudantes ou chamadas e não pode ser excluída.",
      true,
    );
  }
});
$("#session-button").addEventListener("click", async () => {
  if (state.activeSession)
    await api("/session/close", {
      method: "POST",
      body: JSON.stringify({ session_id: state.activeSession }),
    });
  else
    await api("/session/open", {
      method: "POST",
      body: JSON.stringify({ class_id: Number(state.selectedClass) }),
    });
  await refreshSession();
});
$("#enrollment-class").addEventListener("change", loadStudents);
$("#history-class").addEventListener("change", loadHistory);
$("#student-search").addEventListener("input", renderStudents);
$("#kbd-mode-roster").addEventListener("click", () => {
  if (state.kbd.active && state.kbd.context === "roster") exitKeyboardMode();
  else enterKeyboardMode("roster");
});
$("#kbd-mode-history").addEventListener("click", () => {
  if (state.kbd.active && state.kbd.context === "history") exitKeyboardMode();
  else enterKeyboardMode("history");
});
$("#network-shortcut").addEventListener("click", () => showView("network"));

$("#save-network").addEventListener("click", async () => {
  await api("/api/network/config", {
    method: "PUT",
    body: JSON.stringify({
      ssid: $("#ssid").value,
      password: $("#password").value,
    }),
  });
  await loadNetwork();
  toast("Configuração salva.");
});
$("#toggle-network").addEventListener("click", async () => {
  const endpoint = state.network.started ? "stop" : "start";
  try {
    await api(`/api/network/${endpoint}`, { method: "POST" });
    await loadNetwork();
    toast(endpoint === "start" ? "Hotspot iniciado." : "Hotspot encerrado.");
  } catch (e) {
    toast(e.message, true);
    await loadNetwork();
  }
});
$("#windows-hotspot").addEventListener("click", async () => {
  if (window.pywebview?.api?.open_mobile_hotspot_settings) {
    const ok = await window.pywebview.api.open_mobile_hotspot_settings();
    toast(
      ok
        ? "Configurações do Windows abertas."
        : "Não foi possível abrir as configurações.",
      !ok,
    );
  } else {
    toast("Abra Configurações > Rede e Internet > Hotspot Móvel.", true);
  }
});
$("#open-logs").addEventListener("click", async () => {
  if (window.pywebview?.api?.open_log_folder) {
    const ok = await window.pywebview.api.open_log_folder();
    toast(
      ok ? "Pasta de logs aberta." : "Não foi possível abrir a pasta.",
      !ok,
    );
  } else {
    await navigator.clipboard.writeText(state.logInfo.path);
    toast("Caminho copiado.");
  }
});

Promise.all([loadClasses(), loadNetwork()]).catch((error) =>
  toast(error.message, true),
);

$('#network-qr').addEventListener('click', () => window.open($('#network-qr').src, '_blank'));