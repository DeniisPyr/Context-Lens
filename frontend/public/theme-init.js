// Puts the stored theme on the page before it's first drawn, so it never shows in the device's theme first. A classic
// script in the head of index.html runs before anything is drawn, where the app's module runs only after. It's a file
// of its own because the Content Security Policy allows no inline scripts. src/theme.ts holds the same rules.
try {
  const theme = localStorage.getItem('context-lens-theme')
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme
} catch {
  // Storage is blocked, in a private window or by a browser setting: the page follows the device.
}
