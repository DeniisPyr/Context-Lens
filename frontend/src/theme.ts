// System follows the device's setting, and changes with it. Light and Dark hold whatever the device says.
export type Theme = 'system' | 'light' | 'dark'

// public/theme-init.js reads it too, with the same rules, to apply the stored theme before the page is first drawn.
const STORAGE_KEY = 'context-lens-theme'

// Storage can be blocked, in a private window or by a browser setting, and then reading it throws. The page then
// follows the device, as it does for a value it doesn't know.
export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  } catch {
    return 'system'
  }
}

// The theme the page shows now. While storage is blocked, the choice made since the page loaded is only known here.
export function appliedTheme(): Theme {
  const applied = document.documentElement.dataset.theme
  return applied === 'light' || applied === 'dark' ? applied : 'system'
}

// The stylesheet picks the colours from data-theme on <html>. Without it, they follow the device.
export function applyTheme(theme: Theme) {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.dataset.theme = theme
}

// When storage is blocked, the choice still holds until the page reloads.
export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // Nothing to do: applyTheme has already changed the page.
  }
}
