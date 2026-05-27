const keyboard = (() => {
  function init() {
    document.addEventListener('keydown', e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      switch (e.key) {
        case ' ':
          e.preventDefault();
          player.state.playing ? player.pause() : player.resume();
          break;
        case 'ArrowRight':
          e.preventDefault();
          player.seek(Math.min((player.state.duration || 0), (player.state.position || 0) + 5));
          break;
        case 'ArrowLeft':
          e.preventDefault();
          player.seek(Math.max(0, (player.state.position || 0) - 5));
          break;
        case 'n': case 'N':
          player.next();
          break;
        case 'p': case 'P':
          player.prev();
          break;
      }
    });
  }
  return { init };
})();
