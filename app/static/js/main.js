/**
 * MediTrack — Client-side Scripts (Stage 3)
 * Provides: Bootstrap toast notifications, delete confirmations,
 *           auto-dismiss alerts, page-load spinner, and utilities.
 *
 * Loaded on every page via base.html. Each feature is guarded with
 * element existence checks so it won't throw on pages that lack the element.
 */

"use strict";

/* ── Utilities ───────────────────────────────────────────────────────────── */
function el(id) { return document.getElementById(id); }
function qs(sel, ctx) { return (ctx || document).querySelector(sel); }
function qsa(sel, ctx) { return [...(ctx || document).querySelectorAll(sel)]; }

/* ── 1. TOAST SYSTEM ─────────────────────────────────────────────────────── */
/**
 * Show a Bootstrap 5 toast at the top-right corner.
 * @param {string} message  - Text to display
 * @param {'success'|'danger'|'warning'|'info'} type - Bootstrap color variant
 * @param {number} delay    - Auto-hide delay in ms (0 = no auto-hide)
 */
function mtShowToast(message, type = 'info', delay = 4500) {
  let container = el('mt-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'mt-toast-container';
    document.body.appendChild(container);
  }

  const iconMap = {
    success: 'bi-check-circle-fill',
    danger:  'bi-exclamation-octagon-fill',
    warning: 'bi-exclamation-triangle-fill',
    info:    'bi-info-circle-fill',
  };
  const icon = iconMap[type] || iconMap.info;

  const toast = document.createElement('div');
  toast.className = `toast mt-toast show align-items-center text-bg-${type} border-0`;
  toast.setAttribute('role', 'alert');
  toast.setAttribute('aria-live', 'assertive');
  toast.innerHTML = `
    <div class="d-flex align-items-center gap-2 p-3">
      <i class="bi ${icon} fs-5 flex-shrink-0"></i>
      <div class="me-auto">${message}</div>
      <button type="button" class="btn-close btn-close-white ms-2" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>`;

  container.appendChild(toast);

  // Wire Bootstrap dismiss
  const bsToast = new bootstrap.Toast(toast, { autohide: delay > 0, delay });
  bsToast.show();

  // Remove from DOM after hidden
  toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

/* ── 2. CONVERT FLASH ALERTS → TOASTS ───────────────────────────────────── */
/**
 * Existing Flask flash messages rendered as Bootstrap alert divs are
 * converted into toasts and the original alert is hidden immediately.
 * This runs once on DOMContentLoaded.
 */
function convertFlashAlertsToToasts() {
  // Map Bootstrap alert category → toast type
  const categoryMap = {
    success: 'success',
    danger:  'danger',
    error:   'danger',
    warning: 'warning',
    info:    'info',
    primary: 'info',
  };

  qsa('.alert[role="alert"]').forEach(alertEl => {
    // Don't convert the FEFO / patient-allergy inline alerts
    if (alertEl.id === 'patientAllergyAlert') return;
    if (alertEl.closest('#fefoPreviewContainer')) return;

    // Extract the text without the close button
    const closeBtn = alertEl.querySelector('.btn-close');
    if (closeBtn) closeBtn.remove();
    const message = alertEl.innerText.trim();

    // Detect category from class list
    let type = 'info';
    for (const cls of alertEl.classList) {
      const m = cls.match(/^alert-(.+)$/);
      if (m && categoryMap[m[1]]) { type = categoryMap[m[1]]; break; }
    }

    // Hide original alert and show toast
    alertEl.style.display = 'none';
    if (message) mtShowToast(message, type);
  });
}

/* ── 3. AUTO-DISMISS REMAINING ALERTS ────────────────────────────────────── */
/**
 * Any .alert elements NOT converted to toasts auto-dismiss after 6 seconds.
 */
function autoDismissAlerts() {
  qsa('.alert.alert-dismissible:not([style*="display: none"])').forEach(alertEl => {
    if (alertEl.id === 'patientAllergyAlert') return;
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
      if (bsAlert) bsAlert.close();
    }, 6000);
  });
}

/* ── 4. DELETE CONFIRMATION MODALS ──────────────────────────────────────── */
/**
 * Upgrade plain `onsubmit="return confirm(...)` forms with a nicer
 * Bootstrap modal. Add data-mt-confirm="Your message here" to any
 * <form> or <button type="submit"> to enable this.
 *
 * Also handles <a data-mt-confirm="..."> links that trigger a DELETE action.
 */
function setupDeleteConfirmations() {
  // Build a reusable confirm modal if it doesn't exist yet
  if (!el('mt-confirm-modal')) {
    const html = `
    <div class="modal fade" id="mt-confirm-modal" tabindex="-1" aria-hidden="true">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header bg-danger text-white">
            <h5 class="modal-title fw-bold">
              <i class="bi bi-exclamation-triangle-fill me-2"></i>
              <span id="mt-confirm-title">Confirm Action</span>
            </h5>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body" id="mt-confirm-body">
            Are you sure? This action cannot be undone.
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">
              <i class="bi bi-x-lg me-1"></i>Cancel
            </button>
            <button type="button" class="btn btn-danger btn-sm" id="mt-confirm-ok">
              <i class="bi bi-trash me-1"></i>Confirm Delete
            </button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
  }

  const confirmModalEl = el('mt-confirm-modal');
  const confirmModal   = new bootstrap.Modal(confirmModalEl);
  const confirmBody    = el('mt-confirm-body');
  const confirmTitle   = el('mt-confirm-title');
  const confirmOkBtn   = el('mt-confirm-ok');

  let _pendingAction = null; // { type: 'form'|'link', target }

  confirmOkBtn.addEventListener('click', () => {
    confirmModal.hide();
    if (!_pendingAction) return;
    if (_pendingAction.type === 'form') {
      // Submit the form directly (bypass the onsubmit guard)
      _pendingAction.target.removeAttribute('onsubmit');
      _pendingAction.target.submit();
    } else if (_pendingAction.type === 'link') {
      window.location.href = _pendingAction.target;
    }
    _pendingAction = null;
  });

  // Intercept forms with data-mt-confirm
  qsa('form[data-mt-confirm]').forEach(form => {
    // Remove any existing native confirm
    form.removeAttribute('onsubmit');
    form.addEventListener('submit', e => {
      e.preventDefault();
      confirmBody.textContent = form.dataset.mtConfirm || 'Are you sure?';
      confirmTitle.textContent = form.dataset.mtConfirmTitle || 'Confirm Deletion';
      _pendingAction = { type: 'form', target: form };
      confirmModal.show();
    });
  });

  // Also intercept inline onsubmit="return confirm(...)" forms
  // (from the existing batch delete buttons in inventory/view.html)
  qsa('form[onsubmit]').forEach(form => {
    const submitAttr = form.getAttribute('onsubmit') || '';
    if (!submitAttr.includes('confirm(')) return;

    // Extract the message from: return confirm('...')
    const match = submitAttr.match(/confirm\(['"](.+?)['"]\)/);
    const message = match ? match[1] : 'Are you sure?';

    form.removeAttribute('onsubmit');
    form.addEventListener('submit', e => {
      e.preventDefault();
      confirmBody.textContent = message;
      confirmTitle.textContent = 'Confirm Action';
      // Change button label for non-delete actions
      confirmOkBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Yes, Proceed';
      confirmOkBtn.className = 'btn btn-danger btn-sm';
      _pendingAction = { type: 'form', target: form };
      confirmModal.show();
    });
  });
}

/* ── 5. PRINT BUTTON ─────────────────────────────────────────────────────── */
/**
 * Wire any element with [data-mt-print] to trigger window.print().
 */
function setupPrintButtons() {
  qsa('[data-mt-print]').forEach(btn => {
    btn.addEventListener('click', () => window.print());
  });
}

/* ── 6. TABLE SEARCH HIGHLIGHT ───────────────────────────────────────────── */
/**
 * Live client-side filter for tables that have data-mt-search-table="<inputId>".
 * Hides rows whose text doesn't include the search string.
 */
function setupLiveTableSearch() {
  qsa('[data-mt-search-input]').forEach(input => {
    const tableId = input.dataset.mtSearchInput;
    const table = el(tableId);
    if (!table) return;
    const rows = qsa('tbody tr', table);

    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      rows.forEach(row => {
        row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  });
}

/* ── 7. ACTIVE NAV LINK (extra safety) ──────────────────────────────────── */
/**
 * Jinja already sets .active on nav links via endpoint checks.
 * This JS guard only fires if Jinja missed it (e.g. error pages).
 */
function highlightActiveNav() {
  const path = window.location.pathname;
  qsa('.navbar-nav .nav-link').forEach(link => {
    const href = link.getAttribute('href') || '';
    if (href && href !== '/' && path.startsWith(href)) {
      link.classList.add('active');
    }
  });
}

/* ── 8. BACK BUTTON HELPER ───────────────────────────────────────────────── */
qsa('[data-mt-back]').forEach(btn => {
  btn.addEventListener('click', () => window.history.back());
});

/* ── 9. AUTO-FOCUS FIRST INVALID FIELD ON FORM SUBMIT ──────────────────── */
function setupFormValidation() {
  qsa('form.needs-validation').forEach(form => {
    form.addEventListener('submit', e => {
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
        const invalid = qs(':invalid', form);
        if (invalid) invalid.focus();
      }
      form.classList.add('was-validated');
    }, false);
  });
}

/* ── 10. NAVBAR ACTIVE-LINK SCROLL FIX ──────────────────────────────────── */
/* Ensures the active nav pill is visible on mobile after toggle */
function scrollActiveNavIntoView() {
  const active = qs('.navbar-nav .nav-link.active');
  if (active) active.scrollIntoView({ block: 'nearest', inline: 'center' });
}

/* ── BOOT ────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  convertFlashAlertsToToasts();
  autoDismissAlerts();
  setupDeleteConfirmations();
  setupPrintButtons();
  setupLiveTableSearch();
  highlightActiveNav();
  setupFormValidation();
  scrollActiveNavIntoView();
});
