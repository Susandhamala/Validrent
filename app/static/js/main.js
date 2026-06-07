/* ── SIDEBAR TOGGLE ─────────────────────────────────────────── */
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}
document.addEventListener('click', (e) => {
  const sb = document.getElementById('sidebar');
  const toggle = document.getElementById('menuToggle');
  if (sb && !sb.contains(e.target) && toggle && !toggle.contains(e.target)) {
    sb.classList.remove('open');
  }
});

/* ── TOAST NOTIFICATIONS ────────────────────────────────────── */
const TOAST_ICONS = {
  success: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M8 12l3 3 5-5"/></svg>`,
  error:   `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
  info:    `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="16" r="0.5" fill="#3b82f6"/></svg>`,
  warning: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><circle cx="12" cy="17" r="0.5" fill="#f59e0b"/></svg>`,
};

function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    ${TOAST_ICONS[type] || TOAST_ICONS.info}
    <div class="toast-body">${message}</div>
    <span class="toast-close" onclick="removeToast(this.parentElement)">&times;</span>
  `;
  container.appendChild(toast);
  setTimeout(() => removeToast(toast), duration);
}

function removeToast(el) {
  if (!el || !el.parentNode) return;
  el.style.animation = 'toastOut .25s ease forwards';
  setTimeout(() => el.remove(), 250);
}

// Flash messages from server
if (window.__flashMessages) {
  window.__flashMessages.forEach(([cat, msg]) => {
    const type = cat === 'error' ? 'error' : cat === 'success' ? 'success' : cat === 'warning' ? 'warning' : 'info';
    setTimeout(() => showToast(msg, type), 100);
  });
}

/* ── MODAL ──────────────────────────────────────────────────── */
function openModal(html) {
  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('globalModal').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeModal() {
  document.getElementById('globalModal').classList.remove('open');
  document.body.style.overflow = '';
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

/* ── CONFIRM DIALOG ─────────────────────────────────────────── */
function confirmAction(message, formId) {
  openModal(`
    <div class="modal-title">Confirm Action</div>
    <div class="modal-body">${message}</div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="document.getElementById('${formId}').submit(); closeModal()">Confirm</button>
    </div>
  `);
}

/* ── CATEGORY SELECTOR ──────────────────────────────────────── */
function selectCategory(el, inputId) {
  document.querySelectorAll('.category-card').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  const input = document.getElementById(inputId);
  if (input) input.value = el.dataset.value;
}

/* ── FILE UPLOAD PREVIEW ────────────────────────────────────── */
function initFileUpload(inputId, labelId) {
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  if (!input || !label) return;
  input.addEventListener('change', () => {
    const file = input.files[0];
    label.textContent = file ? file.name : 'Choose file...';
  });
}

/* ── WEBCAM ─────────────────────────────────────────────────── */
let webcamStream = null;
let capturedPhoto = null;

async function startWebcam() {
  try {
    const video = document.getElementById('webcamVideo');
    webcamStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    video.srcObject = webcamStream;
    document.getElementById('startCamBtn').style.display = 'none';
    document.getElementById('captureBtn').style.display = 'inline-flex';
    document.getElementById('webcamVideo').style.display = 'block';
  } catch (err) {
    showToast('Camera access denied or unavailable: ' + err.message, 'error');
  }
}

function capturePhoto() {
  const video = document.getElementById('webcamVideo');
  const canvas = document.getElementById('webcamCanvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  capturedPhoto = canvas.toDataURL('image/jpeg', 0.85);

  const preview = document.getElementById('photoPreview');
  if (preview) {
    preview.src = capturedPhoto;
    preview.style.display = 'block';
  }

  // Stop stream
  if (webcamStream) { webcamStream.getTracks().forEach(t => t.stop()); webcamStream = null; }
  document.getElementById('webcamVideo').style.display = 'none';
  document.getElementById('captureBtn').style.display = 'none';
  document.getElementById('retakeBtn').style.display = 'inline-flex';
  document.getElementById('submitPhotoBtn').style.display = 'inline-flex';
  showToast('Photo captured! Review and submit.', 'success');
}

function retakePhoto() {
  capturedPhoto = null;
  document.getElementById('photoPreview').style.display = 'none';
  document.getElementById('retakeBtn').style.display = 'none';
  document.getElementById('submitPhotoBtn').style.display = 'none';
  document.getElementById('startCamBtn').style.display = 'inline-flex';
}

async function submitPhoto(agreementId) {
  const consent = document.getElementById('consentCheck').checked;
  if (!consent) { showToast('You must give consent before submitting.', 'warning'); return; }
  if (!capturedPhoto) { showToast('Please capture a photo first.', 'warning'); return; }

  const btn = document.getElementById('submitPhotoBtn');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const formData = new FormData();
    formData.append('photo_data', capturedPhoto);
    formData.append('consent', 'true');

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
    const headers = {};
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    const res = await fetch(`/photos/save/${agreementId}`, { method: 'POST', headers, body: formData });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      document.getElementById('photoStatus').textContent = '✓ Photo saved successfully';
      document.getElementById('photoStatus').className = 'badge badge-success mt-4';
      btn.style.display = 'none';
    } else {
      showToast(data.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Submit Photo';
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Submit Photo';
  }
}

/* ── POP-IN ON SCROLL ───────────────────────────────────────── */
function initScrollAnimations() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) entry.target.style.animationPlayState = 'running';
    });
  }, { threshold: 0.1 });
  document.querySelectorAll('.pop-in-delay-1, .pop-in-delay-2, .pop-in-delay-3, .pop-in-delay-4, .pop-in-delay-5').forEach(el => {
    el.style.animationPlayState = 'paused';
    observer.observe(el);
  });
}

/* ── INIT ───────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initScrollAnimations();
  initFileUpload('agreementFile', 'fileLabel');
});
