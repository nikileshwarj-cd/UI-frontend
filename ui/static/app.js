/* =====================================================================
   AI Frontend Generation Agent — Control Panel JavaScript
   Handles: form submission, SSE streaming, drag-drop, JSON validation,
            language toggle, pipeline timers, copy-to-clipboard
   ===================================================================== */

'use strict';

// =========================================================================
// Constants / DOM refs
// =========================================================================

const form = document.getElementById('gen-form');
const dropzone = document.getElementById('dropzone');
const imageInput = document.getElementById('image-input');
const imagePreviewWrap = document.getElementById('image-preview-wrap');
const imagePreview = document.getElementById('image-preview');
const previewRemove = document.getElementById('preview-remove');
const storiesTextarea = document.getElementById('stories-textarea');
const jsonStatus = document.getElementById('json-status');
const projectInput = document.getElementById('project-name');
const langInput = document.getElementById('lang-input');
const langBtns = document.querySelectorAll('.lang-btn');
const generateBtn = document.getElementById('generate-btn');
const btnSpinner = document.getElementById('btn-spinner');
const btnText = generateBtn.querySelector('.btn-text');
const loadSampleBtn = document.getElementById('load-sample-btn');
const formatJsonBtn = document.getElementById('format-json-btn');
const copyBtn = document.getElementById('copy-btn');
const runCommandEl = document.getElementById('run-command');
const fileTreeEl = document.getElementById('file-tree');
const coverageBadge = document.getElementById('coverage-badge');
const resultsPanel = document.getElementById('results-panel');
const pipelineIdle = document.getElementById('pipeline-idle');
const pipelineStages = document.getElementById('pipeline-stages');
const pipelineTotal = document.getElementById('pipeline-total');
const totalElapsedEl = document.getElementById('total-elapsed');

function initProjectActions() {
  const proj = projectInput ? projectInput.value.trim() || 'project_1' : 'project_1';
  if (runCommandEl) runCommandEl.textContent = `cd "output/${proj}" && npm install && npm run dev`;
}
initProjectActions();

if (projectInput) {
  projectInput.addEventListener('input', () => {
    const proj = projectInput.value.trim() || 'project_1';
    if (runCommandEl) runCommandEl.textContent = `cd "output/${proj}" && npm install && npm run dev`;
  });
}

// =========================================================================
// Sample user stories
// =========================================================================

const SAMPLE_STORIES = [
  {
    "id": "US101",
    "title": "User Login",
    "description": "As a user, I want to log in with my email and password so I can access the application.",
    "acceptanceCriteria": [
      "Email field is visible and validates email format",
      "Password field is masked and required",
      "Login button submits the form",
      "Error message appears on invalid credentials"
    ]
  },
  {
    "id": "US102",
    "title": "Navigation",
    "description": "As a user, I want a navigation bar so I can move between sections.",
    "acceptanceCriteria": [
      "Navigation links are visible",
      "Active link is highlighted",
      "Navigation is responsive on mobile"
    ]
  },
  {
    "id": "US103",
    "title": "Dashboard View",
    "description": "As a user, I want to see a dashboard with key metrics after logging in.",
    "acceptanceCriteria": [
      "Dashboard shows summary cards",
      "Cards display relevant data",
      "Dashboard is accessible via the /dashboard route"
    ]
  }
];

// =========================================================================
// Image Drag & Drop
// =========================================================================

// Guard flag — prevents stacking multiple file dialogs when the user
// clicks the dropzone repeatedly while the OS picker is slow to open.
function openFilePicker() {
  if (imageInput) imageInput.click();
}

// Clicking anywhere on the dropzone opens the file picker
if (dropzone) {
  dropzone.addEventListener('click', (e) => {
    if (e.target === imageInput) return;
    openFilePicker();
  });
}

dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('drag-over');
});

dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));

dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleImageFile(file);
});

imageInput.addEventListener('change', () => {
  if (imageInput.files[0]) handleImageFile(imageInput.files[0]);
});

function handleImageFile(file) {
  const allowed = ['.png', '.jpg', '.jpeg', '.webp'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!allowed.includes(ext)) {
    showToast('Unsupported file type. Use PNG, JPG, or WEBP.', 'error');
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    imagePreview.src = e.target.result;
    imagePreviewWrap.hidden = false;
    dropzone.hidden = true;
  };
  reader.readAsDataURL(file);

  // Sync to file input
  const dt = new DataTransfer();
  dt.items.add(file);
  imageInput.files = dt.files;
}

previewRemove.addEventListener('click', () => {
  imagePreview.src = '';
  imagePreviewWrap.hidden = true;
  dropzone.hidden = false;
  imageInput.value = '';
});

// Keyboard accessibility for dropzone
dropzone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    openFilePicker();
  }
});

// =========================================================================
// JSON Validation
// =========================================================================

let jsonValidateTimeout;

storiesTextarea.addEventListener('input', () => {
  clearTimeout(jsonValidateTimeout);
  jsonValidateTimeout = setTimeout(validateJson, 400);
});

function validateJson() {
  const text = storiesTextarea.value.trim();
  if (!text) {
    jsonStatus.textContent = '';
    jsonStatus.className = 'json-status';
    return;
  }
  try {
    JSON.parse(text);
    jsonStatus.textContent = '✓ Valid JSON';
    jsonStatus.className = 'json-status valid';
  } catch (e) {
    jsonStatus.textContent = `✗ ${e.message}`;
    jsonStatus.className = 'json-status invalid';
  }
}

// =========================================================================
// Load Sample / Format JSON
// =========================================================================

loadSampleBtn.addEventListener('click', () => {
  storiesTextarea.value = JSON.stringify(SAMPLE_STORIES, null, 2);
  validateJson();
});

formatJsonBtn.addEventListener('click', () => {
  try {
    const parsed = JSON.parse(storiesTextarea.value);
    storiesTextarea.value = JSON.stringify(parsed, null, 2);
    validateJson();
  } catch (e) {
    storiesTextarea.classList.add('shake');
    setTimeout(() => storiesTextarea.classList.remove('shake'), 500);
  }
});

// =========================================================================
// Language Toggle
// =========================================================================

langBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    langBtns.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed', 'false'); });
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    langInput.value = btn.dataset.lang;
  });
});

// =========================================================================
// Pipeline State
// =========================================================================

const stageTimers = {}; // stageNum → { start, interval }
let pipelineTotalStart = null;
let totalTimer = null;

function startStageTimer(stageNum) {
  const timeEl = document.getElementById(`stage-${stageNum}-time`);
  const start = Date.now();
  stageTimers[stageNum] = {
    start,
    interval: setInterval(() => {
      const elapsed = Math.floor((Date.now() - start) / 1000);
      timeEl.textContent = formatTime(elapsed);
    }, 500)
  };
}

function stopStageTimer(stageNum) {
  if (stageTimers[stageNum]) {
    clearInterval(stageTimers[stageNum].interval);
    delete stageTimers[stageNum];
  }
}

function startTotalTimer() {
  pipelineTotalStart = Date.now();
  pipelineTotal.hidden = false;
  totalTimer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - pipelineTotalStart) / 1000);
    totalElapsedEl.textContent = formatTime(elapsed);
  }, 500);
}

function stopTotalTimer() {
  if (totalTimer) { clearInterval(totalTimer); totalTimer = null; }
}

function formatTime(seconds) {
  const m = String(Math.floor(seconds / 60)).padStart(2, '0');
  const s = String(seconds % 60).padStart(2, '0');
  return `${m}:${s}`;
}

function setStageStatus(stageNum, status) {
  const item = document.getElementById(`stage-${stageNum}`);
  const icon = document.getElementById(`stage-${stageNum}-icon`);

  item.className = `stage-item ${status}`;
  icon.className = `stage-icon ${status}`;

  const icons = { pending: '○', running: '◉', done: '✓', failed: '✗' };
  icon.textContent = icons[status] || '○';
}

function addLogLine(stageNum, msg) {
  const log = document.getElementById(`stage-${stageNum}-log`);
  const line = document.createElement('div');
  line.className = 'log-line';
  line.textContent = msg;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

// =========================================================================
// Form Submission + SSE
// =========================================================================

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  // Validate
  if (!imageInput.files[0]) {
    showToast('Please upload a reference UI screenshot.', 'error');
    document.getElementById('dropzone') || dropzone.classList.add('shake');
    return;
  }

  const storiesText = storiesTextarea.value.trim();
  if (!storiesText) {
    showToast('Please provide user stories JSON.', 'error');
    return;
  }

  try { JSON.parse(storiesText); }
  catch (e) {
    showToast('User stories JSON is invalid. Please fix and retry.', 'error');
    storiesTextarea.classList.add('shake');
    setTimeout(() => storiesTextarea.classList.remove('shake'), 500);
    return;
  }

  // UI: start
  setGenerating(true);
  resetPipeline();
  resultsPanel.hidden = true;
  pipelineIdle.hidden = true;
  pipelineStages.style.display = 'flex';
  startTotalTimer();

  // Build form data
  const fd = new FormData();
  fd.append('image', imageInput.files[0]);
  fd.append('stories', storiesText);
  fd.append('project', projectInput.value.trim() || 'generated-app');
  fd.append('lang', langInput.value);

  let sessionId;
  try {
    const res = await fetch('/generate', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || `Server error ${res.status}`);
    }
    const data = await res.json();
    sessionId = data.session_id;
  } catch (err) {
    showToast(`Failed to start generation: ${err.message}`, 'error');
    setGenerating(false);
    stopTotalTimer();
    pipelineIdle.hidden = false;
    return;
  }

  // SSE
  const evtSource = new EventSource(`/stream/${sessionId}`);

  evtSource.addEventListener('stage_start', (e) => {
    const d = JSON.parse(e.data);
    setStageStatus(d.stage, 'running');
    startStageTimer(d.stage);
  });

  evtSource.addEventListener('log', (e) => {
    const d = JSON.parse(e.data);
    addLogLine(d.stage, d.message);
  });

  evtSource.addEventListener('stage_done', (e) => {
    const d = JSON.parse(e.data);
    stopStageTimer(d.stage);
    setStageStatus(d.stage, 'done');
    const timeEl = document.getElementById(`stage-${d.stage}-time`);
    timeEl.textContent = formatTime(d.elapsed || 0);

    // Add completion info to log
    const infos = [];
    if (d.elements) infos.push(`${d.elements} elements`);
    if (d.pages) infos.push(`${d.pages} pages`);
    if (d.mappings) infos.push(`${d.mappings} mappings`);
    if (d.coverage !== undefined) infos.push(`${d.coverage}% coverage`);
    if (infos.length) addLogLine(d.stage, `✓ Done — ${infos.join(', ')}`);
  });

  evtSource.addEventListener('stage_fail', (e) => {
    const d = JSON.parse(e.data);
    stopStageTimer(d.stage);
    setStageStatus(d.stage, 'failed');
    addLogLine(d.stage, `✗ ${d.error || 'Failed'}`);
  });

  evtSource.addEventListener('error', (e) => {
    try {
      const d = JSON.parse(e.data);
      showToast(`Error: ${d.message}`, 'error');
    } catch (_) { }
  });

  evtSource.addEventListener('done', (e) => {
    const d = JSON.parse(e.data);
    evtSource.close();
    stopTotalTimer();
    setGenerating(false);

    if (d.success) {
      const project = d.project || (projectInput ? projectInput.value.trim() : 'my-generated-app');
      const reactPath = `output/${project}`;
      if (runCommandEl) runCommandEl.textContent = `cd "${reactPath}" && npm install && npm run dev`;

      const downloadBtn = document.getElementById('download-btn');
      const deleteBtn = document.getElementById('delete-btn');
      if (downloadBtn) downloadBtn.href = `/download/${project}`;
      if (deleteBtn) deleteBtn.dataset.project = project;

      if (d.file_tree && fileTreeEl) fileTreeEl.textContent = d.file_tree;
      if (d.coverage !== undefined && coverageBadge) {
        coverageBadge.textContent = `Coverage: ${d.coverage}%`;
        coverageBadge.hidden = false;
      }
      if (resultsPanel) {
        resultsPanel.hidden = false;
        resultsPanel.classList.add('fade-in');
      }
      showToast('Frontend generated successfully! 🎉', 'success');
    } else {
      showToast('Generation failed. Check the pipeline logs for details.', 'error');
    }
  });

  evtSource.onerror = (err) => {
    // If browser is reconnecting or waiting for model response, continue listening
    if (evtSource.readyState === EventSource.CONNECTING) {
      console.warn('SSE connection waiting for server updates...');
      return;
    }
    evtSource.close();
    stopTotalTimer();
    setGenerating(false);
  };
});

// =========================================================================
// UI Helpers
// =========================================================================

function setGenerating(active) {
  generateBtn.disabled = active;
  btnSpinner.hidden = !active;
  btnText.textContent = active ? 'Generating...' : 'Generate Frontend';
}

function resetPipeline() {
  [1, 2, 3, 4].forEach(n => {
    setStageStatus(n, 'pending');
    document.getElementById(`stage-${n}-log`).innerHTML = '';
    document.getElementById(`stage-${n}-time`).textContent = '—';
    stopStageTimer(n);
  });
}

// Copy command
copyBtn.addEventListener('click', () => {
  navigator.clipboard.writeText(runCommandEl.textContent).then(() => {
    copyBtn.textContent = 'Copied!';
    copyBtn.classList.add('copied');
    setTimeout(() => {
      copyBtn.textContent = 'Copy';
      copyBtn.classList.remove('copied');
    }, 2000);
  });
});

// =========================================================================
// Toast notification helper
// =========================================================================

let toastTimeout;

function showToast(msg, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    document.body.appendChild(toast);
    Object.assign(toast.style, {
      position: 'fixed',
      bottom: '24px',
      right: '24px',
      padding: '12px 20px',
      borderRadius: '10px',
      fontSize: '0.85rem',
      fontFamily: 'Inter, sans-serif',
      fontWeight: '500',
      maxWidth: '360px',
      zIndex: '9999',
      backdropFilter: 'blur(20px)',
      border: '1px solid',
      transition: 'all 0.3s ease',
      opacity: '0',
      transform: 'translateY(10px)',
    });
  }

  const styles = {
    success: { bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.4)', color: '#34d399' },
    error: { bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.4)', color: '#f87171' },
    info: { bg: 'rgba(99,102,241,0.12)', border: 'rgba(99,102,241,0.4)', color: '#a5b4fc' },
  };

  const s = styles[type] || styles.info;
  toast.style.background = s.bg;
  toast.style.borderColor = s.border;
  toast.style.color = s.color;
  toast.textContent = msg;

  clearTimeout(toastTimeout);
  toast.style.opacity = '1';
  toast.style.transform = 'translateY(0)';

  toastTimeout = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
  }, 4000);
}
