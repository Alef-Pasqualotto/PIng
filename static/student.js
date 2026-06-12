const select = document.querySelector('#class-select');
const button = document.querySelector('#checkin-button');
const stateBox = document.querySelector('#session-state');
const message = document.querySelector('#student-message');
const deviceText = document.querySelector('#student-device');

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
    stateBox.className = 'status neutral'; stateBox.textContent = 'Selecione uma turma.'; button.disabled = true; return;
  }
  try {
    const data = await api(`/session/status?class_id=${select.value}`);
    stateBox.className = `status ${data.is_open ? 'success' : 'warning'}`;
    stateBox.textContent = data.is_open ? 'Chamada aberta. Você já pode confirmar.' : 'A chamada ainda não está aberta.';
    button.disabled = !data.is_open;
  } catch (error) { stateBox.className = 'status error'; stateBox.textContent = error.message; button.disabled = true; }
}

button.addEventListener('click', async () => {
  button.disabled = true; button.textContent = 'Confirmando...';
  
  try {
    const data = await api('/checkin', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({device_id: deviceId(), class_id: Number(select.value)})});
    if (!data.is_enrolled) {
      message.className = 'message warning-text'; message.textContent = 'Seu dispositivo foi identificado, mas você ainda não está matriculado nesta turma. Avise o professor.';
    } else {
      message.className = 'message success-text'; message.textContent = 'Presença confirmada. Você pode fechar esta página.';
    }
    console.log(data)
  } catch (error) { message.className = 'message error-text'; message.textContent = error.message; }
  button.textContent = 'Confirmar presença';
});

select.addEventListener('change', updateStatus);
setInterval(updateStatus, 5000);
function escapeHtml(value) { const el = document.createElement('span'); el.textContent = value ?? ''; return el.innerHTML; }
loadClasses();
displayDeviceId();
