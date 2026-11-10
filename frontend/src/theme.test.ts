import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyTheme, readTheme, saveTheme } from './theme.ts'

const KEY = 'context-lens-theme'

// What a browser throws when its storage is blocked.
const blocked = () => {
  throw new DOMException('The operation is insecure.', 'SecurityError')
}

afterEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  vi.restoreAllMocks()
})

describe('readTheme', () => {
  it.each(['system', 'light', 'dark'])('gives back a stored %s', (theme) => {
    localStorage.setItem(KEY, theme)

    expect(readTheme()).toBe(theme)
  })

  it('follows the device when nothing is stored', () => {
    expect(readTheme()).toBe('system')
  })

  it.each(['', 'Dark', 'sepia'])('follows the device when the stored value is %j, which it does not know', (value) => {
    localStorage.setItem(KEY, value)

    expect(readTheme()).toBe('system')
  })

  it('follows the device when storage is blocked', () => {
    localStorage.setItem(KEY, 'dark')
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked)

    expect(readTheme()).toBe('system')
  })
})

describe('applyTheme', () => {
  it.each(['light', 'dark'] as const)('marks the page as %s', (theme) => {
    applyTheme(theme)

    expect(document.documentElement).toHaveAttribute('data-theme', theme)
  })

  it('takes the mark off for System, so the colours follow the device', () => {
    applyTheme('dark')
    applyTheme('system')

    expect(document.documentElement).not.toHaveAttribute('data-theme')
  })
})

describe('saveTheme', () => {
  it('stores the choice, so readTheme finds it after a reload', () => {
    saveTheme('dark')

    expect(localStorage.getItem(KEY)).toBe('dark')
    expect(readTheme()).toBe('dark')
  })

  it('does not throw when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked)

    expect(() => saveTheme('light')).not.toThrow()
    expect(localStorage.getItem(KEY)).toBeNull()
  })
})
