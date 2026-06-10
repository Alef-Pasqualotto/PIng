const state = {classes: [], selectedClass: null, activeSession: null, rosterTimer: null, network: null};
const $ = selector => document.querySelector(selector);

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Não foi possível concluir a operação.');
  return data;
}

function toast(text, error = false) {
  const el = $('#toast'); el.textContent = text; el.style.background = error ? '#b42318' : '#17202d'; el.classList.add('show');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove('show'), 3200);
}

function esc(value) { const el = document.createElement('span'); el.textContent = value ?? ''; return el.innerHTML; }
function currentClass() { return state.classes.find(item => item.id === Number(state.selectedClass)); }

async function loadClasses(keepSelection = true) {
  const previous = keepSelection ? Number(state.selectedClass) : null;
  state.classes = await api('/classes');
  state.selectedClass = state.classes.some(c => c.id === previous) ? previous : (state.classes[0]?.id || null);
  for (const selector of ['#class-picker', '#enrollment-class', '#history-class']) {
    const el = $(selector);
    el.innerHTML = state.classes.length ? state.classes.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('') : '<option value="">Nenhuma turma</option>';
    if (state.selectedClass) el.value = state.selectedClass;
  }
  await refreshSession();
}

async function refreshSession() {
  clearInterval(state.rosterTimer); state.rosterTimer = null; state.activeSession = null;
  const cls = currentClass();
  $('#delete-class').disabled = !cls; $('#session-button').disabled = !cls;
  if (!cls) { $('#session-title').textContent = 'Nenhuma turma selecionada'; $('#session-description').textContent = 'Crie uma turma para iniciar.'; renderRoster([]); return; }
  $('#session-title').textContent = cls.name;
  const status = await api(`/session/status?class_id=${cls.id}`);
  state.activeSession = status.is_open ? status.session_id : null;
  $('#session-description').textContent = status.is_open ? 'A chamada está aberta e recebendo confirmações.' : 'Nenhuma chamada aberta para esta turma.';
  $('#session-button').textContent = status.is_open ? 'Encerrar chamada' : 'Abrir chamada';
  $('#session-button').className = status.is_open ? 'secondary' : 'primary';
  if (state.activeSession) {
    await loadRoster(); state.rosterTimer = setInterval(loadRoster, 3000);
  } else renderRoster([]);
}

async function loadRoster() {
  if (!state.activeSession) return;
  try { renderRoster(await api(`/session/${state.activeSession}/roster`)); } catch (error) { toast(error.message, true); }
}

function renderRoster(rows) {
  $('#present-count').textContent = rows.filter(r => r.present).length;
  $('#absent-count').textContent = rows.filter(r => !r.present).length;
  $('#roster-empty').style.display = rows.length ? 'none' : 'block';
  $('#roster-empty').textContent = state.activeSession ? 'Nenhum estudante matriculado nesta turma.' : 'Abra uma chamada para acompanhar as presenças.';
  $('#roster-list').innerHTML = rows.map(r => `<div class="table-row"><div><div class="student-name">${esc(r.student_name || 'Nome não informado')}</div><div class="small">${esc(r.device_id)}</div></div><span class="badge ${r.present ? 'success' : 'warning'}">${r.present ? 'Presente' : 'Ausente'}</span><div class="row-actions"><button class="mini present" data-attendance-student="${r.student_id}" data-present="true">Presente</button><button class="mini absent" data-attendance-student="${r.student_id}" data-present="false">Ausente</button></div></div>`).join('');
}

async function setAttendance(studentId, present) {
  await api(`/session/${state.activeSession}/students/${studentId}/attendance`, {method:'PUT', body:JSON.stringify({present})}); await loadRoster();
}

async function loadStudents() {
  const students = await api('/students');
  const classId = Number($('#enrollment-class').value);
  const enrolled = classId ? await api(`/classes/${classId}/students`) : [];
  const enrolledIds = new Set(enrolled.map(s => s.id));
  $('#students-list').innerHTML = students.length ? students.map(s => `<div class="table-row"><div><div class="student-name">${esc(s.name || 'Nome não informado')}</div><div class="small">${esc(s.device_id)}</div></div><button class="mini" data-edit-student="${s.id}" data-name="${esc(s.name || '')}">Editar nome</button><div class="row-actions"><button class="mini ${enrolledIds.has(s.id) ? 'absent' : 'present'}" data-enroll-student="${s.id}" data-enrolled="${enrolledIds.has(s.id)}">${enrolledIds.has(s.id) ? 'Remover da turma' : 'Matricular'}</button></div></div>`).join('') : '<div class="empty">Nenhum estudante conhecido. Peça aos estudantes para abrirem a página de presença.</div>';
}

async function loadHistory() {
  const classId = Number($('#history-class').value);
  if (!classId) { $('#history-list').innerHTML = '<div class="empty">Crie uma turma para ver o histórico.</div>'; return; }
  const sessions = await api(`/classes/${classId}/sessions`);
  $('#history-list').innerHTML = sessions.length ? sessions.map(s => `<div class="table-row"><div><div class="student-name">Chamada de ${esc(s.date)}</div><div class="small">Sessão #${s.id}</div></div><span class="badge ${s.is_open ? 'success' : 'neutral'}">${s.is_open ? 'Aberta' : 'Encerrada'}</span><div class="row-actions"><button class="mini" data-review-session="${s.id}">Ver lista</button><button class="mini" data-export-session="${s.id}">Exportar CSV</button></div></div>`).join('') : '<div class="empty">Nenhuma chamada registrada para esta turma.</div>';
}

async function reviewSession(id) {
  const rows = await api(`/session/${id}/roster`);
  const summary = rows.map(r => `${r.present ? '✓' : '–'} ${r.student_name || r.device_id}`).join('\n') || 'Nenhum estudante nesta chamada.';
  alert(summary);
}

async function exportSession(id) {
  if (window.pywebview?.api?.save_csv) {
    const result = await window.pywebview.api.save_csv(id); if (result) toast('Arquivo CSV salvo.');
  } else window.location.href = `/session/${id}/export`;
}

async function loadNetwork() {
  const [network, logInfo] = await Promise.all([api('/api/network/status'), api('/api/debug/log-info')]);
  state.network = network; state.logInfo = logInfo;
  $('#student-url').textContent = state.network.student_url; $('#network-url-detail').textContent = state.network.student_url;
  $('#network-qr').src = `/api/network/qr?t=${Date.now()}`;
  $('#ssid').value = state.network.ssid; $('#password').value = state.network.password;
  $('#network-badge').className = `badge ${state.network.started ? 'success' : 'neutral'}`; $('#network-badge').textContent = state.network.started ? 'Hotspot ativo' : 'Rede existente';
  $('#network-hint').textContent = state.network.started ? `Conecte os celulares à rede “${state.network.ssid}” e abra o endereço.` : 'Conecte computador e celulares à mesma rede e abra este endereço.';
  $('#compatibility').className = `status ${state.network.compatibility.supported ? 'success' : 'warning'}`; $('#compatibility').textContent = state.network.compatibility.detail;
  $('#toggle-network').textContent = state.network.started ? 'Parar hotspot' : 'Iniciar hotspot';
  $('#toggle-network').disabled = !state.network.started && !state.network.compatibility.supported;
  $('#windows-hotspot').style.display = state.network.compatibility.supported ? 'none' : 'inline-block';
  $('#log-path').textContent = logInfo.path;
}

function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
  document.querySelectorAll('.nav-item').forEach(v => v.classList.toggle('active', v.dataset.view === name));
  $('#view-title').textContent = {dashboard:'Visão geral',students:'Estudantes',history:'Histórico',network:'Rede da sala'}[name];
  if (name === 'students') loadStudents().catch(e => toast(e.message,true));
  if (name === 'history') loadHistory().catch(e => toast(e.message,true));
  if (name === 'network') loadNetwork().catch(e => toast(e.message,true));
}

function promptModal(title, text, value = '') {
  const dialog = $('#modal'); $('#modal-title').textContent = title; $('#modal-text').textContent = text; $('#modal-input').value = value; dialog.showModal();
  return new Promise(resolve => { dialog.addEventListener('close', () => resolve(dialog.returnValue === 'default' ? $('#modal-input').value.trim() : null), {once:true}); });
}

document.addEventListener('click', async event => {
  const nav = event.target.closest('[data-view]'); if (nav) return showView(nav.dataset.view);
  const attendance = event.target.closest('[data-attendance-student]'); if (attendance) return setAttendance(Number(attendance.dataset.attendanceStudent), attendance.dataset.present === 'true').catch(e=>toast(e.message,true));
  const edit = event.target.closest('[data-edit-student]'); if (edit) { const name = await promptModal('Editar estudante','Informe o nome que aparecerá nas listas.',edit.dataset.name); if (name) { await api(`/students/${edit.dataset.editStudent}/name`,{method:'PATCH',body:JSON.stringify({name})}); await loadStudents(); } return; }
  const enroll = event.target.closest('[data-enroll-student]'); if (enroll) { const body=JSON.stringify({class_id:Number($('#enrollment-class').value),student_id:Number(enroll.dataset.enrollStudent)}); await api('/enrollments',{method:enroll.dataset.enrolled==='true'?'DELETE':'POST',body}); await loadStudents(); return; }
  const review = event.target.closest('[data-review-session]'); if (review) return reviewSession(review.dataset.reviewSession);
  const exp = event.target.closest('[data-export-session]'); if (exp) return exportSession(exp.dataset.exportSession);
});

$('#class-picker').addEventListener('change', async e => { state.selectedClass=Number(e.target.value); document.querySelectorAll('#enrollment-class,#history-class').forEach(x=>x.value=state.selectedClass); await refreshSession(); });
$('#add-class').addEventListener('click', async () => { const name=await promptModal('Criar turma','Informe um nome curto, como “3º A - Matemática”.'); if(name){const c=await api('/classes',{method:'POST',body:JSON.stringify({name})});state.selectedClass=c.id;await loadClasses();toast('Turma criada.');} });
$('#delete-class').addEventListener('click', async () => { const cls=currentClass(); if(!cls||!confirm(`Excluir a turma “${cls.name}”? Esta ação só é permitida quando não há registros vinculados.`))return;try{await api(`/classes/${cls.id}`,{method:'DELETE'});await loadClasses(false);toast('Turma excluída.')}catch(e){toast('A turma possui estudantes ou chamadas e não pode ser excluída.',true)}});
$('#session-button').addEventListener('click', async () => { if(state.activeSession) await api('/session/close',{method:'POST',body:JSON.stringify({session_id:state.activeSession})});else await api('/session/open',{method:'POST',body:JSON.stringify({class_id:Number(state.selectedClass)})});await refreshSession(); });
$('#enrollment-class').addEventListener('change', loadStudents); $('#history-class').addEventListener('change', loadHistory);
$('#network-shortcut').addEventListener('click',()=>showView('network')); $('#copy-url').addEventListener('click',async()=>{await navigator.clipboard.writeText(state.network.student_url);toast('Endereço copiado.')});
$('#save-network').addEventListener('click',async()=>{await api('/api/network/config',{method:'PUT',body:JSON.stringify({ssid:$('#ssid').value,password:$('#password').value})});await loadNetwork();toast('Configuração salva.')});
$('#toggle-network').addEventListener('click',async()=>{const endpoint=state.network.started?'stop':'start';try{await api(`/api/network/${endpoint}`,{method:'POST'});await loadNetwork();toast(endpoint==='start'?'Hotspot iniciado.':'Hotspot encerrado.')}catch(e){toast(e.message,true);await loadNetwork()}});
$('#windows-hotspot').addEventListener('click',async()=>{if(window.pywebview?.api?.open_mobile_hotspot_settings){const ok=await window.pywebview.api.open_mobile_hotspot_settings();toast(ok?'Configurações do Windows abertas.':'Não foi possível abrir as configurações.',!ok)}else{toast('Abra Configurações > Rede e Internet > Hotspot Móvel.',true)}});
$('#open-logs').addEventListener('click',async()=>{if(window.pywebview?.api?.open_log_folder){const ok=await window.pywebview.api.open_log_folder();toast(ok?'Pasta de logs aberta.':'Não foi possível abrir a pasta.',!ok)}else{await navigator.clipboard.writeText(state.logInfo.path);toast('Caminho copiado.')}});
$('#copy-log-path').addEventListener('click',async()=>{await navigator.clipboard.writeText(state.logInfo.path);toast('Caminho do log copiado.')});

Promise.all([loadClasses(), loadNetwork()]).catch(error => toast(error.message, true));
