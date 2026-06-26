const select = document.querySelector('#class-select');
const button = document.querySelector('#checkin-button');
const stateBox = document.querySelector('#session-state');
const message = document.querySelector('#student-message');
const checkinVisual = document.querySelector('#checkin-visual');
const checkinIcon = document.querySelector('#checkin-icon');
const checkinTitle = document.querySelector('#checkin-title');
const checkinDetail = document.querySelector('#checkin-detail');
const deviceText = document.querySelector('#student-device');
const absencesBtn = document.querySelector('#view-absences-button');
const absencesDialog = document.querySelector('#absences-dialog');
const absencesTableBody = document.querySelector('#absences-table-body');
const absencesClassName = document.querySelector('#absences-class-name');
const absencesSummary = document.querySelector('#absences-summary');
const closeAbsencesBtn = document.querySelector('#close-absences');

function deviceId() {
  let id = localStorage.getItem('ping-device-id');
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : `device-${Date.now()}-${Math.random()}`);
    localStorage.setItem('ping-device-id', id);
  }
  return id;
}

async function displayDeviceId(){
  deviceText.textContent = 'Nome do dispositivo: ' + deviceId();
}

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Não foi possível concluir a operação.');
  return data;
}

async function loadClasses() {
  try {
    const classes = await api('/public/classes');
    select.innerHTML = '<option value="">Selecione sua turma</option>' + classes.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
  } catch (error) {
    select.innerHTML = '<option value="">Servidor indisponível</option>';
    message.textContent = error.message;
  }
}

async function updateStatus() {
  message.textContent = '';
  if (!select.value) {
    stateBox.className = 'status neutral'; stateBox.textContent = 'Selecione uma turma.'; button.disabled = true; absencesBtn.disabled = true; setVisual('neutral', '•', 'Aguardando confirmação', 'Selecione uma turma para começar.'); return;
  }
  try {
    const data = await api(`/session/status?class_id=${select.value}`);
    stateBox.className = `status ${data.is_open ? 'success' : 'warning'}`;
    stateBox.textContent = data.is_open ? 'Chamada aberta. Você já pode confirmar.' : 'A chamada ainda não está aberta.';
    button.disabled = !data.is_open;
    absencesBtn.disabled = false;
    if (!data.is_open) setVisual('warning', '!', 'Chamada fechada', 'Aguarde o professor abrir a chamada.');
  } catch (error) { stateBox.className = 'status error'; stateBox.textContent = error.message; button.disabled = true; absencesBtn.disabled = true; }
}

button.addEventListener('click', async () => {
  button.disabled = true; button.textContent = 'Confirmando...';
  
  try {
    const data = await api('/checkin', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device_id: deviceId(), class_id: Number(select.value)})});
    if (!data.is_enrolled) {
      message.className = 'message warning-text'; message.textContent = 'Seu dispositivo foi identificado, mas você ainda não está matriculado nesta turma. Avise o professor.';
      setVisual('warning', '!', 'Dispositivo não matriculado', 'Peça ao professor para vincular este dispositivo à turma.');
    } else if (data.already_present) {
      message.className = 'message success-text'; message.textContent = 'Sua presença já estava confirmada.';
      setVisual('already', '✓', 'Você já está presente', 'Não precisa confirmar de novo. O professor já recebeu sua presença.');
    } else {
      message.className = 'message success-text'; message.textContent = 'Presença confirmada. Você pode fechar esta página.';
      setVisual('success', '✓', 'Presença confirmada', 'O professor recebeu sua confirmação agora.');
    }
  } catch (error) { message.className = 'message error-text'; message.textContent = error.message; }
  button.textContent = 'Confirmar presença';
});

select.addEventListener('change', updateStatus);
setInterval(updateStatus, 5000);

absencesBtn.addEventListener('click', async () => {
  if (!select.value) return;
  absencesBtn.disabled = true;
  absencesBtn.textContent = 'Carregando...';
  try {
    const classText = select.options[select.selectedIndex].text;
    const data = await api(`/public/students/attendance?device_id=${deviceId()}&class_id=${select.value}`);
    absencesClassName.textContent = classText;
    
    let presentCount = 0;
    let absentCount = 0;
    let justifiedCount = 0;
    let falsifiedCount = 0;
    
    absencesTableBody.innerHTML = data.history.length 
      ? data.history.map(row => {
          let statusText = 'Ausente';
          let badgeClass = 'badge warning';
          if (row.present === 1) {
            statusText = row.duration_percentage !== null && row.duration_percentage !== undefined 
              ? `Presente (${row.duration_percentage}%)`
              : 'Presente';
            badgeClass = 'badge success'; presentCount++;
          } else if (row.present === 2) {
            statusText = 'Justificada'; badgeClass = 'badge neutral'; justifiedCount++;
          } else if (row.present === 3) {
            statusText = 'Falsificada'; badgeClass = 'badge error'; falsifiedCount++;
          } else {
            absentCount++;
          }
          return `
            <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
              <td style="padding: 10px 12px; font-size: 0.9rem;">${escapeHtml(row.date)}</td>
              <td style="padding: 10px 12px; text-align: right;"><span class="${badgeClass}" style="font-size: 0.75rem;">${statusText}</span></td>
            </tr>
          `;
        }).join('')
      : '<tr><td colspan="2" style="text-align: center; padding: 20px;" class="muted">Nenhuma chamada registrada.</td></tr>';
      
    absencesSummary.innerHTML = data.history.length 
      ? `Presenças: <strong>${presentCount}</strong> &nbsp; Faltas: <strong>${absentCount}</strong>`
      : '';
    absencesDialog.showModal();
  } catch (error) {
    alert(error.message);
  } finally {
    absencesBtn.disabled = false;
    absencesBtn.textContent = 'Ver minhas presenças';
  }
});

closeAbsencesBtn.addEventListener('click', () => {
  absencesDialog.close();
});

function escapeHtml(value) { const el = document.createElement('span'); el.textContent = value ?? ''; return el.innerHTML; }
function setVisual(kind, icon, title, detail) {
  checkinVisual.className = `checkin-visual ${kind}`;
  checkinIcon.textContent = icon;
  checkinTitle.textContent = title;
  checkinDetail.textContent = detail;
}
loadClasses();
displayDeviceId();
