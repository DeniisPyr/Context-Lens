// System follows the device's setting, and changes with it. Light and Dark hold whatever the device says.
export type Theme = 'system' | 'light' | 'dark'

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
