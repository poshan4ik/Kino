/* Aurora staff.js — generic CRUD / modal / table helpers для staff-страниц. */
(function () {
  'use strict';

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function confirmMsg(msg) {
    return window.confirm(msg || 'Вы уверены?');
  }

  function formPayload(form) {
    var hasFile = !!form.querySelector('input[type="file"]');
    var fd = new FormData(form);
    if (hasFile) {
      var filesOk = true;
      qsa('input[type="file"]', form).forEach(function (input) {
        if (!input.files.length && input.required) filesOk = false;
      });
      if (!filesOk) return { error: 'Выберите файл' };
      Array.prototype.forEach.call(fd, function (val, key) {
        if (val === '' && form.elements[key] && form.elements[key].type !== 'file') {
          /* пустые строки отправляем как есть — сериализаторы решают */
        }
      });
      return fd;
    }
    var data = {};
    Array.prototype.forEach.call(fd, function (val, key) {
      var node = form.elements[key];
      if (!node) { data[key] = val; return; }
      if (node.type === 'checkbox') { data[key] = node.checked; }
      else if (node.type === 'number') { data[key] = val === '' ? null : Number(val); }
      else { data[key] = val; }
    });
    return data;
  }

  function reloadSoon(ms) {
    setTimeout(function () { window.location.reload(); }, ms || 600);
  }

  /* ── Forms with data-crud ─────────────────────────────── */
  document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-crud]');
    if (!form) return;
    e.preventDefault();
    if (form.dataset.busy === '1') return;

    var payload = formPayload(form);
    if (payload && payload.error) { window.Aurora.toast(payload.error, 'error'); return; }

    var method = (form.dataset.method || 'POST').toUpperCase();
    var url = form.dataset.url;
    var success = form.dataset.success || 'Сохранено';
    var btn = form.querySelector('[type="submit"]');
    if (btn) { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = 'Сохранение…'; }
    form.dataset.busy = '1';

    window.Aurora.api(method, url, payload)
      .then(function () {
        window.Aurora.toast(success, 'success');
        if (form.dataset.reload === '0') {
          form.dataset.busy = '0';
          if (btn) { btn.disabled = false; btn.textContent = btn.dataset.label; }
          window.location.assign(window.location.pathname + window.location.search);
        } else {
          reloadSoon(400);
        }
      })
      .catch(function (err) {
        form.dataset.busy = '0';
        if (btn) { btn.disabled = false; btn.textContent = btn.dataset.label; }
        var detail = err.message || 'Ошибка сохранения';
        if (err.payload && typeof err.payload === 'object') {
          var parts = [];
          Object.keys(err.payload).forEach(function (k) {
            var v = err.payload[k];
            parts.push(k + ': ' + (Array.isArray(v) ? v.join(', ') : v));
          });
          if (parts.length) detail = parts.join('\n');
        }
        window.Aurora.toast(detail, 'error');
      });
  });

  /* ── Delete buttons ───────────────────────────────────── */
  document.addEventListener('click', function (e) {
    var del = e.target.closest('[data-api-delete]');
    if (del) {
      if (!confirmMsg(del.getAttribute('data-confirm') || 'Удалить запись?')) return;
      var url = del.getAttribute('data-url');
      del.disabled = true;
      window.Aurora.api('DELETE', url)
        .then(function () {
          window.Aurora.toast(del.getAttribute('data-success') || 'Удалено', 'success');
          if (del.getAttribute('data-no-reload') === '1') {
            var row = del.closest('tr');
            if (row) row.remove();
          } else {
            reloadSoon(400);
          }
        })
        .catch(function (err) {
          del.disabled = false;
          window.Aurora.toast(err.message || 'Не удалось удалить', 'error');
        });
      return;
    }

    /* generic POST action (generate_seats и т.п.) */
    var act = e.target.closest('[data-api-action]');
    if (act) {
      if (act.getAttribute('data-confirm') && !confirmMsg(act.getAttribute('data-confirm'))) return;
      var actUrl = act.getAttribute('data-url');
      var actBody = {};
      try {
        var raw = act.getAttribute('data-api-body');
        if (raw) actBody = JSON.parse(raw);
      } catch (parseErr) { /* пустое тело */ }
      var oldLabel = act.textContent;
      act.disabled = true;
      window.Aurora.api('POST', actUrl, actBody)
        .then(function (res) {
          window.Aurora.toast((res && res.detail) || act.getAttribute('data-success') || 'Готово', 'success');
          if (act.getAttribute('data-no-reload') !== '1') reloadSoon(500);
          else { act.disabled = false; act.textContent = oldLabel; }
        })
        .catch(function (err) {
          act.disabled = false;
          act.textContent = oldLabel;
          window.Aurora.toast(err.message || 'Ошибка', 'error');
        });
      return;
    }

    /* toggle field PATCH (is_active и т.п.) */
    var tog = e.target.closest('[data-toggle-field]');
    if (tog) {
      var tUrl = tog.getAttribute('data-url');
      var field = tog.getAttribute('data-toggle-field');
      var cur = tog.getAttribute('data-value') === 'true';
      tog.disabled = true;
      window.Aurora.api('PATCH', tUrl, define1(field, !cur))
        .then(function () {
          window.Aurora.toast('Обновлено', 'success');
          reloadSoon(350);
        })
        .catch(function (err) {
          tog.disabled = false;
          window.Aurora.toast(err.message || 'Ошибка', 'error');
        });
      return;
    }

    /* open/close modals */
    var opener = e.target.closest('[data-modal-open]');
    if (opener) {
      var modal = document.querySelector(opener.getAttribute('data-modal-open'));
      if (modal) {
        fillForm(modal, opener);
        modal.classList.add('open');
        var first = modal.querySelector('input,select,textarea');
        if (first) setTimeout(function () { first.focus(); }, 120);
      }
      return;
    }
    var closer = e.target.closest('[data-modal-close]');
    if (closer) {
      var m = closer.closest('.modal-overlay');
      if (m) m.classList.remove('open');
      return;
    }
    if (e.target.classList && e.target.classList.contains('modal-overlay')) {
      e.target.classList.remove('open');
    }
  });

  function define1(field, value) {
    var o = {};
    o[field] = value;
    return o;
  }

  function fillForm(modal, src) {
    var form = modal.querySelector('form');
    if (!form) return;
    if (!form.getAttribute('data-default-url')) {
      form.setAttribute('data-default-url', form.dataset.url || '');
    }
    var defaultUrl = form.getAttribute('data-default-url');
    form.reset();
    var title = modal.querySelector('[data-form-title]');
    if (src.hasAttribute('data-fill')) {
      Array.prototype.forEach.call(src.attributes, function (attr) {
        if (attr.name.indexOf('data-field-') !== 0) return;
        var name = attr.name.slice('data-field-'.length);
        var node = form.elements[name];
        if (!node) return;
        if (node.type === 'checkbox') node.checked = attr.value === 'true';
        else node.value = attr.value;
      });
      var idField = form.elements['id'];
      if (idField) idField.value = src.getAttribute('data-id') || '';
      form.dataset.url = src.getAttribute('data-url') || defaultUrl;
      form.dataset.method = src.getAttribute('data-method') || 'PUT';
      if (title && src.getAttribute('data-title')) title.textContent = src.getAttribute('data-title');
    } else {
      form.dataset.method = 'POST';
      form.dataset.url = defaultUrl;
      if (title && src.getAttribute('data-title')) title.textContent = src.getAttribute('data-title');
    }
  }

  /* Esc closes open modal */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      qsa('.modal-overlay.open').forEach(function (m) { m.classList.remove('open'); });
    }
  });

  /* ── Status filter select → GET ───────────────────────── */
  document.addEventListener('change', function (e) {
    var sel = e.target.closest('[data-filter-select]');
    if (sel) {
      var url = new URL(window.location.href);
      var param = sel.getAttribute('data-filter-select');
      if (sel.value) url.searchParams.set(param, sel.value);
      else url.searchParams.delete(param);
      window.location.href = url.toString();
    }
  });

  /* ── Live table search [data-table-search="#tbl"] ─────── */
  document.addEventListener('input', function (e) {
    var inp = e.target.closest('[data-table-search]');
    if (!inp) return;
    var table = document.querySelector(inp.getAttribute('data-table-search'));
    if (!table) return;
    var term = inp.value.trim().toLowerCase();
    qsa('tbody tr', table).forEach(function (row) {
      var text = row.textContent.toLowerCase();
      row.classList.toggle('hidden-row', !!term && text.indexOf(term) === -1);
    });
  });

  /* QR codes in staff tables */
  document.addEventListener('DOMContentLoaded', function () {
    if (window.Aurora && window.Aurora.renderQR) window.Aurora.renderQR(document);
  });
})();
