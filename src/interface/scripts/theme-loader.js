const ThemeLoader = (() => {
  let _current = 'dark';

  async function load(name) {
    const url = `../styles/themes/${name}.json`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Theme not found: ${name}`);
    const theme = await res.json();
    const root = document.documentElement;
    Object.entries(theme.colors || {}).forEach(([k, v]) => {
      root.style.setProperty(`--color-${k}`, v);
    });
    Object.entries(theme.typography || {}).forEach(([k, v]) => {
      root.style.setProperty(`--font-${k}`, v);
    });
    _current = name;
    document.documentElement.setAttribute('data-theme', name);
  }

  function current() { return _current; }

  return { load, current };
})();
