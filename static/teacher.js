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
    "#grades-class",
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
function badgeHtml(present) {
  switch (present) {
    case 1:
      return '<span class="badge success">Presente</span>';
    case 2:
      return '<span class="badge neutral">Justificada</span>';
    case 3:
      return '<span class="badge error">Falsificada</span>';
    case 0:
    default:
      return '<span class="badge warning">Ausente</span>';
  }
}

function formatDuration(present, percentage) {
  if (present !== 1) return "";
  if (percentage === null || percentage === undefined) return "";
  return ` (${percentage}% da aula)`;
}

function rowActionsHtml(r, context) {
  const isHistory = context === "history";
  const attrName = isHistory ? "data-history-attendance" : "data-attendance-student";
  const valAttr = isHistory ? r.attendance_id : r.student_id;
  const checkoutButton = (r.present === 1) ? (
    r.checked_out_at ?
      `<button title="Limpar Saída" class="mini-btn checkout-btn active" data-student-id="${r.student_id}" data-checkout="false" data-context="${context}">Retornar</button>` :
      `<button title="Registrar Saída" class="mini-btn checkout-btn" data-student-id="${r.student_id}" data-checkout="true" data-context="${context}">Saída</button>`
  ) : "";
  return `
    <div class="mini-btn-group">
      <button title="Presente" class="mini-btn present ${r.present === 1 ? 'active' : ''}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" ${attrName}="${valAttr}" data-status="1">P</button>
      <button title="Ausente" class="mini-btn absent ${r.present === 0 ? 'active' : ''}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" ${attrName}="${valAttr}" data-status="0">A</button>
      <button title="Ausência Justificada" class="mini-btn justified ${r.present === 2 ? 'active' : ''}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" ${attrName}="${valAttr}" data-status="2">J</button>
      <button title="Presença Falsificada" class="mini-btn falsified ${r.present === 3 ? 'active' : ''}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" ${attrName}="${valAttr}" data-status="3">F</button>
      ${checkoutButton}
    </div>
  `;
}

function renderRoster(rows) {
  state._rosterRows = rows;
  $("#present-count").textContent = rows.filter((r) => r.present === 1).length;
  $("#absent-count").textContent = rows.filter((r) => r.present === 0).length;
  $("#justified-count").textContent = rows.filter((r) => r.present === 2).length;
  $("#falsified-count").textContent = rows.filter((r) => r.present === 3).length;
  $("#roster-empty").style.display = rows.length ? "none" : "block";
  $("#roster-empty").textContent = state.activeSession
    ? "Nenhum estudante matriculado nesta turma."
    : "Abra uma chamada para acompanhar as presenças.";
  $("#kbd-mode-roster").disabled = !rows.length;
  $("#roster-list").innerHTML = rows
    .map(
      (r) => {
        const checkedOutClass = r.checked_out_at ? "checked-out" : "";
        return `<div class="table-row roster-row ${checkedOutClass}" data-attendance-id="${r.attendance_id}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" data-student-id="${r.student_id}"><div><div class="student-name">${esc(r.student_name || "Nome não informado")}${formatDuration(r.present, r.duration_percentage)}</div><div class="small">${esc(r.device_id)}</div></div>${badgeHtml(r.present)}${rowActionsHtml(r, "roster")}</div>`;
      }
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
          <button class="mini" data-merge-student="${s.id}" data-name="${esc(s.name || "")}">Mesclar</button>
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
  $("#history-present-count").textContent = rows.filter((r) => r.present === 1).length;
  $("#history-absent-count").textContent = rows.filter((r) => r.present === 0).length;
  $("#history-justified-count").textContent = rows.filter((r) => r.present === 2).length;
  $("#history-falsified-count").textContent = rows.filter((r) => r.present === 3).length;
  $("#history-roster-list").innerHTML = rows.length
    ? rows
      .map(
        (r) => {
          const checkedOutClass = r.checked_out_at ? "checked-out" : "";
          return `<div class="table-row roster-row ${checkedOutClass}" data-attendance-id="${r.attendance_id}" data-class-id="${state.selectedClass}" data-device-id="${r.device_id}" data-student-id="${r.student_id}"><div><div class="student-name">${esc(r.student_name || "Nome não informado")}${formatDuration(r.present, r.duration_percentage)}</div><div class="small">${esc(r.device_id)}</div></div>${badgeHtml(r.present)}${rowActionsHtml(r, "history")}</div>`;
        }
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
    "Chamada rápida ativa.",
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
  const device_id = row.getAttribute("data-device-id");
  const class_id = Number(row.getAttribute("data-class-id"));
  if (!row) return;
  let attendanceId;
  if (row.dataset.attendanceId != "null" && row.dataset.attendanceId != "undefined" && row.dataset.attendanceId != "") {
    attendanceId = row.dataset.attendanceId;
  } else {
    attendanceId = -1;
  }
  try {
    const data = await api(`/attendance/${attendanceId}`, {
      method: "PATCH",
      body: JSON.stringify({ device_id, class_id, present }),
    });

    // Update attendance ID if we got a new one back from -1
    if (attendanceId == -1 && data.attendance_id) {
      row.dataset.attendanceId = data.attendance_id;
    }

    // Update badge and active class inline without a full reload
    const badge = row.querySelector(".badge");
    if (present === 1) {
      badge.className = "badge success"; badge.textContent = "Presente";
    } else if (present === 2) {
      badge.className = "badge neutral"; badge.textContent = "Justificada";
    } else if (present === 3) {
      badge.className = "badge error"; badge.textContent = "Falsificada";
    } else {
      badge.className = "badge warning"; badge.textContent = "Ausente";
    }

    row.querySelectorAll(".mini-btn").forEach(btn => {
      btn.classList.toggle("active", Number(btn.dataset.status) === present);
    });

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
  const key = e.key.toLowerCase();
  if (["1", "2", "3", "4", "tab", "p", "a", "j", "f"].includes(key)) {
    e.preventDefault();
  } else {
    return;
  }
  if (key === "1" || key === "p") await kbdSetAttendance(state.kbd.context, 1);
  else if (key === "2" || key === "a") await kbdSetAttendance(state.kbd.context, 0);
  else if (key === "3" || key === "j") await kbdSetAttendance(state.kbd.context, 2);
  else if (key === "4" || key === "f") await kbdSetAttendance(state.kbd.context, 3);
  else if (key === "tab") kbdAdvance(state.kbd.context);
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
    grades: "Avaliações",
    network: "Rede da sala",
  }[name];
  if (name === "students") loadStudents().catch((e) => toast(e.message, true));
  if (name === "history") loadHistory().catch((e) => toast(e.message, true));
  if (name === "grades") loadGrades().catch((e) => toast(e.message, true));
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

function promptMergeModal(targetId, targetName) {
  const dialog = $("#merge-modal");
  $("#merge-target-name").textContent = targetName;
  const select = $("#merge-source-select");
  const otherStudents = (state._students || []).filter(s => s.id !== Number(targetId));
  
  if (otherStudents.length === 0) {
    select.innerHTML = '<option value="">Nenhum outro estudante cadastrado</option>';
  } else {
    otherStudents.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    select.innerHTML = otherStudents
      .map(s => `<option value="${s.id}">${esc(s.name || "Nome não informado")} (${esc(s.device_id)})</option>`)
      .join("");
  }
  
  dialog.showModal();
  return new Promise((resolve) => {
    dialog.addEventListener(
      "close",
      () => {
        resolve(
          dialog.returnValue === "default" && select.value
            ? Number(select.value)
            : null
        );
      },
      { once: true }
    );
  });
}

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) return showView(nav.dataset.view);
  const attendance = event.target.closest("[data-attendance-student]");

  if (attendance)

    return setAttendance(
      Number(attendance.dataset.attendanceStudent),
      attendance.getAttribute("data-device-id"),
      attendance.getAttribute("data-class-id"),
      attendance.getAttribute("data-status"),
    ).catch((e) => toast(e.message, true));

  const checkoutBtn = event.target.closest(".checkout-btn");
  if (checkoutBtn) {
    const studentId = Number(checkoutBtn.dataset.studentId);
    const checkout = checkoutBtn.dataset.checkout === "true";
    const context = checkoutBtn.dataset.context;
    const sessionId = context === "history" ? state._historySessionId : state.activeSession;
    try {
      await api(`/session/${sessionId}/students/${studentId}/checkout`, {
        method: "PUT",
        body: JSON.stringify({ checkout })
      });
      if (context === "history") {
        await reviewSession(
          state._historySessionId,
          $("#history-roster-title").textContent.replace("Chamada de ", ""),
        );
      } else {
        await loadRoster();
      }
      toast(checkout ? "Saída registrada." : "Saída cancelada.");
    } catch (e) {
      toast(e.message, true);
    }
    return;
  }

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
  const mergeBtn = event.target.closest("[data-merge-student]");
  if (mergeBtn) {
    const targetId = Number(mergeBtn.dataset.mergeStudent);
    const targetName = mergeBtn.dataset.name || "Nome não informado";
    const sourceId = await promptMergeModal(targetId, targetName);
    if (sourceId) {
      try {
        await api(`/students/${targetId}/merge`, {
          method: "POST",
          body: JSON.stringify({ source_id: sourceId }),
        });
        await loadStudents();
        toast("Estudantes mesclados com sucesso.");
      } catch (e) {
        toast(e.message, true);
      }
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

  const addTest = event.target.closest("#add-test");
  if (addTest) {
    const classId = Number($("#grades-class").value);
    if (!classId) return;
    const name = await promptModal("Criar avaliação", "Informe o nome da prova/trabalho.");
    if (!name) return;
    const maxScoreStr = await promptModal("Nota máxima", "Informe o valor máximo da avaliação.", "10.0");
    const maxScore = maxScoreStr ? Number(maxScoreStr) : 10.0;
    if (isNaN(maxScore) || maxScore <= 0) {
      toast("Nota máxima inválida.", true);
      return;
    }
    await api("/tests", {
      method: "POST",
      body: JSON.stringify({ class_id: classId, name, max_score: maxScore })
    });
    await loadGrades();
    toast("Avaliação criada.");
    return;
  }

  const deleteTestBtn = event.target.closest("[data-delete-test]");
  if (deleteTestBtn) {
    const testId = Number(deleteTestBtn.dataset.deleteTest);
    if (!confirm("Excluir esta avaliação permanentemente? Todos os registros de notas serão apagados.")) return;
    await api(`/tests/${testId}`, { method: "DELETE" });
    await loadGrades();
    toast("Avaliação excluída.");
    return;
  }

  const editMaxBtn = event.target.closest(".edit-max-btn");
  if (editMaxBtn) {
    const testId = Number(editMaxBtn.dataset.editMaxTestId);
    const testName = editMaxBtn.dataset.testName;
    const currentMax = editMaxBtn.dataset.currentMax;
    const newMaxStr = await promptModal(
      `Editar nota máxima: ${testName}`,
      `Informe a nova nota máxima para esta avaliação (nota atual: ${currentMax}).`,
      currentMax
    );
    if (!newMaxStr) return;
    const newMax = Number(newMaxStr);
    if (isNaN(newMax) || newMax <= 0) {
      toast("Nota máxima inválida.", true);
      return;
    }
    try {
      await api(`/tests/${testId}/max-score`, {
        method: "PATCH",
        body: JSON.stringify({ max_score: newMax })
      });
      await loadGrades();
      toast("Nota máxima atualizada.");
    } catch (e) {
      toast(e.message, true);
    }
    return;
  }
});

$("#class-picker").addEventListener("change", async (e) => {
  state.selectedClass = Number(e.target.value);
  document
    .querySelectorAll("#enrollment-class,#history-class,#grades-class")
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

$("#grades-class").addEventListener("change", loadGrades);

$("#modal-cancel").addEventListener("click", () => {
  $("#modal").close("cancel");
});
$("#merge-cancel").addEventListener("click", () => {
  $("#merge-modal").close("cancel");
});

document.addEventListener("change", async (event) => {
  const gradeInput = event.target.closest(".grade-input");
  if (gradeInput) {
    const studentId = Number(gradeInput.dataset.studentId);
    const testId = Number(gradeInput.dataset.testId);
    const maxScore = Number(gradeInput.dataset.maxScore);
    const val = gradeInput.value.trim();
    try {
      await updateGrade(studentId, testId, val, maxScore);
      toast("Nota salva.");
    } catch (e) {
      toast(e.message, true);
      await loadGrades();
    }
  }
});

// ---------------------------------------------------------------------------
// Grades & Tests management (Spreadsheet Grid View)
// ---------------------------------------------------------------------------

async function loadGrades() {
  const classId = Number($("#grades-class").value);
  if (!classId) {
    $("#gradebook-container").innerHTML = '<div class="empty">Selecione uma turma para ver as avaliações.</div>';
    return;
  }

  const [students, tests] = await Promise.all([
    api(`/classes/${classId}/students`),
    api(`/classes/${classId}/tests`)
  ]);

  const allGrades = await Promise.all(tests.map(t => api(`/tests/${t.id}/grades`)));

  const gradesMap = {};
  students.forEach(s => {
    gradesMap[s.id] = {};
  });

  tests.forEach((t, idx) => {
    const testGrades = allGrades[idx];
    testGrades.forEach(g => {
      if (gradesMap[g.student_id]) {
        gradesMap[g.student_id][t.id] = g.score;
      }
    });
  });

  if (students.length === 0) {
    $("#gradebook-container").innerHTML = '<div class="empty">Nenhum estudante matriculado nesta turma.</div>';
    return;
  }

  $("#gradebook-container").innerHTML = `
    <div class="gradebook-wrapper">
      <table class="gradebook-table">
        <thead>
          <tr>
            <th>Estudante</th>
            ${tests.map(t => `
              <th class="test-header" data-test-id="${t.id}">
                <div class="test-header-content">
                  <span class="test-name" title="${esc(t.name)}">${esc(t.name)}</span>
                  <button class="edit-max-btn" data-edit-max-test-id="${t.id}" data-test-name="${esc(t.name)}" data-current-max="${t.max_score}" title="Editar nota máxima">
                    Máx: ${t.max_score} ✏️
                  </button>
                  <button class="delete-test-btn" data-delete-test="${t.id}" title="Excluir avaliação">×</button>
                </div>
              </th>
            `).join("")}
            ${tests.length > 0 ? `<th>Total</th>` : ""}
          </tr>
        </thead>
        <tbody>
          ${students.map(s => {
    const studentSum = tests.reduce((sum, t) => sum + (gradesMap[s.id][t.id] || 0), 0);
    return `
              <tr>
                <td class="student-cell">
                  <div class="student-name">${esc(s.name || "Nome não informado")}</div>
                  <div class="small">${esc(s.device_id)}</div>
                </td>
                ${tests.map(t => {
      const score = gradesMap[s.id][t.id];
      const scoreVal = (score !== null && score !== undefined) ? score : "";
      return `
                    <td class="grade-cell">
                      <input type="number" step="0.1" min="0" max="${t.max_score}" 
                             class="grade-input" 
                             data-student-id="${s.id}" 
                             data-test-id="${t.id}" 
                             data-max-score="${t.max_score}" 
                             value="${scoreVal}" 
                             placeholder="—">
                    </td>
                  `;
    }).join("")}
                ${tests.length > 0 ? `
                  <td class="total-cell" data-student-id="${s.id}" style="font-weight: 700; text-align: center; color: var(--ink);">
                    ${studentSum.toFixed(1)}
                  </td>
                ` : ""}
              </tr>
            `;
  }).join("")}
        </tbody>
        ${tests.length > 0 ? `
          <tfoot>
            <tr class="average-row">
              <td>Média da Turma</td>
              ${tests.map((t, idx) => {
    const testGrades = allGrades[idx];
    const scores = testGrades.map(g => g.score).filter(sc => sc !== null && sc !== undefined);
    let avgStr = "—";
    if (scores.length > 0) {
      const sum = scores.reduce((a, b) => a + b, 0);
      avgStr = (sum / scores.length).toFixed(1);
    }
    return `<td class="average-cell" data-average-test-id="${t.id}">${avgStr}</td>`;
  }).join("")}
              <td class="total-cell" style="font-weight: 700; text-align: center; color: var(--muted); font-size: 13px;">
                Máx: ${tests.reduce((acc, curr) => acc + curr.max_score, 0).toFixed(1)}
              </td>
            </tr>
          </tfoot>
        ` : ""}
      </table>
    </div>
  `;
}

async function updateGrade(studentId, testId, scoreVal, maxScore) {
  const score = scoreVal === "" ? null : Number(scoreVal);

  if (score !== null) {
    if (isNaN(score) || score < 0) {
      toast("Nota inválida.", true);
      return;
    }
    if (score > maxScore) {
      toast(`A nota não pode superar a nota máxima (${maxScore}).`, true);
      return;
    }
  }

  await api(`/tests/${testId}/students/${studentId}/grade`, {
    method: "PUT",
    body: JSON.stringify({ score })
  });

  // Recalculate average for this specific test column
  const inputs = Array.from(document.querySelectorAll(`.grade-input[data-test-id="${testId}"]`));
  const scores = inputs.map(input => input.value === "" ? null : Number(input.value)).filter(s => s !== null);
  const avgCell = document.querySelector(`.average-cell[data-average-test-id="${testId}"]`);
  if (avgCell) {
    if (scores.length === 0) {
      avgCell.textContent = "—";
    } else {
      const sum = scores.reduce((a, b) => a + b, 0);
      avgCell.textContent = (sum / scores.length).toFixed(1);
    }
  }

  // Recalculate total for this student row
  const studentInputs = Array.from(document.querySelectorAll(`.grade-input[data-student-id="${studentId}"]`));
  const studentSum = studentInputs.map(input => input.value === "" ? 0 : Number(input.value)).reduce((a, b) => a + b, 0);
  const totalCell = document.querySelector(`.total-cell[data-student-id="${studentId}"]`);
  if (totalCell) {
    totalCell.textContent = studentSum.toFixed(1);
  }
}