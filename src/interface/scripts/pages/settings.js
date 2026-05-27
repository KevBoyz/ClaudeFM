const settingsPage = (() => {
  let _settings = {};

  async function render(container, params = {}) {
    container.innerHTML = `
      <div class="page-header"><h1 class="page-title">Settings</h1></div>
      <div id="settings-skeleton" class="page-skeleton"></div>
      <div id="settings-body" style="display:none"></div>`;

    try {
      _settings = await api.get_settings();
    } catch (e) {
      document.getElementById('settings-body').innerHTML = `<div class="error-state">${e.message}</div>`;
      document.getElementById('settings-skeleton').style.display = 'none';
      document.getElementById('settings-body').style.display = 'block';
      return;
    }

    document.getElementById('settings-skeleton').style.display = 'none';
    const body = document.getElementById('settings-body');
    body.style.display = 'block';

    body.innerHTML = `
      <div class="settings-section">
        <h2>Account</h2>
        <div class="settings-row" id="row-apikey">
          <span class="settings-label">Last.fm API Key</span>
          <div class="settings-field">
            <input type="text" id="set-apikey" value="${_settings.lastfm_api_key || ''}" placeholder="Enter API key" />
            <button class="btn btn-ghost" id="set-test">Test Connection</button>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h2>Library</h2>
        <div class="settings-row" id="row-folder">
          <span class="settings-label">Download Folder</span>
          <div class="settings-field">
            <input type="text" id="set-folder" value="${_settings.download_folder || ''}" placeholder="e.g. C:\\Music" />
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Audio Format</span>
          <div class="settings-field settings-radio-group">
            <label><input type="radio" name="fmt" value="m4a" ${(_settings.audio_format||'m4a')==='m4a'?'checked':''}> m4a</label>
            <label><input type="radio" name="fmt" value="mp3" ${_settings.audio_format==='mp3'?'checked':''}> mp3</label>
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Auto-fetch lyrics</span>
          <div class="settings-field">
            <label class="settings-toggle">
              <input type="checkbox" id="set-autolyr" ${_settings.auto_fetch_lyrics==='true'?'checked':''}>
              <span class="settings-toggle-track"></span>
            </label>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h2>Search</h2>
        <div class="settings-row">
          <span class="settings-label">Results limit</span>
          <div class="settings-field">
            <select id="set-limit">
              ${[1,3,5,10,15,20].map(n =>
                `<option value="${n}" ${parseInt(_settings.search_results_limit||5)===n?'selected':''}>${n}</option>`
              ).join('')}
            </select>
          </div>
        </div>
        <div class="settings-row">
          <span class="settings-label">Cache enabled</span>
          <div class="settings-field">
            <label class="settings-toggle">
              <input type="checkbox" id="set-cache" ${_settings.cache_enabled!=='false'?'checked':''}>
              <span class="settings-toggle-track"></span>
            </label>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h2>Appearance</h2>
        <div class="settings-row">
          <span class="settings-label">Theme</span>
          <div class="settings-field">
            <select id="set-theme">
              <option value="dark"  ${(_settings.theme||'dark')==='dark' ?'selected':''}>Dark</option>
              <option value="light" ${_settings.theme==='light'?'selected':''}>Light</option>
            </select>
          </div>
        </div>
      </div>

      <button class="btn btn-primary" id="set-save">Save Settings</button>`;

    document.getElementById('set-test').addEventListener('click', async () => {
      const btn = document.getElementById('set-test');
      btn.disabled = true; btn.textContent = '⏳';
      try {
        await api.save_setting('lastfm_api_key', document.getElementById('set-apikey').value.trim());
        await api.check_lastfm_connection();
        toast.show('Connected to Last.fm', 'success', 3000);
      } catch (e) {
        toast.show('Last.fm connection failed: ' + e.message, 'error', 5000);
      }
      btn.disabled = false; btn.textContent = 'Test Connection';
    });

    document.getElementById('set-save').addEventListener('click', async () => {
      const btn = document.getElementById('set-save');
      btn.disabled = true;
      try {
        const oldFolder = _settings.download_folder || '';
        const newFolder = document.getElementById('set-folder').value.trim();
        const fmt = document.querySelector('[name=fmt]:checked')?.value || 'm4a';
        await Promise.all([
          api.save_setting('lastfm_api_key',       document.getElementById('set-apikey').value.trim()),
          api.save_setting('download_folder',       newFolder),
          api.save_setting('audio_format',          fmt),
          api.save_setting('auto_fetch_lyrics',     document.getElementById('set-autolyr').checked ? 'true' : 'false'),
          api.save_setting('search_results_limit',  document.getElementById('set-limit').value),
          api.save_setting('cache_enabled',         document.getElementById('set-cache').checked ? 'true' : 'false'),
          api.save_setting('theme',                 document.getElementById('set-theme').value),
        ]);
        ThemeLoader.load(document.getElementById('set-theme').value);
        _settings.download_folder = newFolder;
        if (newFolder && newFolder !== oldFolder) {
          api.rescan_library();
          toast.show('Settings saved — scanning library…', 'success', 3000);
        } else {
          toast.show('Settings saved', 'success', 2000);
        }
      } catch (e) {
        toast.show('Failed to save settings: ' + (e.message || e), 'error', 5000);
      } finally {
        btn.disabled = false;
      }
    });

    if (params.highlight) {
      const fieldId = params.highlight === 'apikey' ? 'row-apikey' : 'row-folder';
      const el = document.getElementById(fieldId);
      if (el) {
        el.classList.add('settings-highlight');
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => el.classList.remove('settings-highlight'), 3000);
      }
    }
  }

  function destroy() {}

  router.register('settings', (c, p) => settingsPage.render(c, p));

  return { render, destroy };
})();
