const toast = (() => {
  const MAX = 3;
  const _active = [];

  function show(message, type = 'info', duration = 3000) {
    if (_active.length >= MAX) {
      const oldest = _active.shift();
      oldest.remove();
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    document.getElementById('toast-container').appendChild(el);
    _active.push(el);
    requestAnimationFrame(() => { el.classList.add('visible'); });
    setTimeout(() => {
      el.classList.remove('visible');
      el.addEventListener('transitionend', () => {
        el.remove();
        const i = _active.indexOf(el);
        if (i !== -1) _active.splice(i, 1);
      }, { once: true });
    }, duration);
  }

  return { show };
})();
