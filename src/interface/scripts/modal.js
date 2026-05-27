const modal = (() => {
  const _c = () => document.getElementById('modal-container');

  function hide() { _c().classList.add('hidden'); _c().innerHTML = ''; }

  function _show(html) {
    _c().innerHTML = `<div class="modal">${html}</div>`;
    _c().classList.remove('hidden');
  }

  function confirm(message, title = 'Confirm', okLabel = 'Delete') {
    return new Promise(resolve => {
      _show(`<h3>${title}</h3><p>${message}</p>
        <div class="modal-actions">
          <button class="btn btn-ghost" id="m-cancel">Cancel</button>
          <button class="btn btn-danger" id="m-ok">${okLabel}</button>
        </div>`);
      document.getElementById('m-cancel').onclick = () => { hide(); resolve(false); };
      document.getElementById('m-ok').onclick     = () => { hide(); resolve(true); };
    });
  }

  function prompt(message, placeholder = '') {
    return new Promise(resolve => {
      _show(`<p>${message}</p>
        <input id="m-input" type="text" placeholder="${placeholder}" />
        <div class="modal-actions">
          <button class="btn btn-ghost" id="m-cancel">Cancel</button>
          <button class="btn btn-primary" id="m-ok">OK</button>
        </div>`);
      const input = document.getElementById('m-input');
      input.focus();
      const ok = () => { const v = input.value.trim(); hide(); resolve(v || null); };
      document.getElementById('m-cancel').onclick = () => { hide(); resolve(null); };
      document.getElementById('m-ok').onclick = ok;
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter') ok();
        if (e.key === 'Escape') { hide(); resolve(null); }
      });
    });
  }

  return { confirm, prompt, hide };
})();
