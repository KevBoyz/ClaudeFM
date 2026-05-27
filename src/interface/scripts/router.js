const router = (() => {
  const _pages = {};
  const _history = [];
  let _current = null;
  const _container = () => document.getElementById('main-content');

  function register(route, renderFn) {
    _pages[route] = renderFn;
  }

  async function navigate(route, params = {}) {
    const render = _pages[route];
    if (!render) { console.warn(`router: no page for route "${route}"`); return; }
    if (_current && typeof _current.destroy === 'function') _current.destroy();
    _history.push({ route, params });
    _current = null;
    _container().innerHTML = '<div class="page-skeleton"></div>';
    document.querySelectorAll('[data-route]').forEach(el => {
      el.classList.toggle('active', el.dataset.route === route.split('/')[0]);
    });
    try {
      await render(_container(), params);
    } catch (e) {
      _container().innerHTML = `<p class="error-state">Failed to load page: ${e.message}</p>`;
      console.error('router render error', e);
    }
  }

  function back() {
    if (_history.length > 1) {
      _history.pop();
      const prev = _history[_history.length - 1];
      navigate(prev.route, prev.params);
    }
  }

  function current() { return _current; }

  function init() {
    // Route registrations — overwritten by page scripts at load time
    ['home','artists','albums','lastfm/artist','lastfm/album',
     'playlists','playlist-detail','downloads','settings'].forEach(r => {
      if (!_pages[r]) {
        register(r, (c) => {
          c.innerHTML = `<p style="color:var(--color-text_secondary);padding:16px">Loading: ${r}</p>`;
        });
      }
    });
    navigate('home');
  }

  return { register, navigate, back, current, init };
})();
