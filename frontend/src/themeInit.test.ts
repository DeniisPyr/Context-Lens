import { afterEach, describe, expect, it, vi } from 'vitest'
import script from '../public/theme-init.js?raw'

// public/theme-init.js runs as a classic script in index.html's head, before the app. Here its source runs the same
// way, as a plain script against jsdom's page and storage.
const run = () => new Function(script)()

const KEY = 'context-lens-theme'
const html = document.documentElement

afterEach(() => {
  localStorage.clear()
  html.removeAttribute('data-theme')
  vi.restoreAllMocks()
})

describe('theme-init.js', () => {
  it.each(['light', 'dark'])('marks the page as %s when that is stored', (theme) => {
    localStorage.setItem(KEY, theme)

    run()

    expect(html).toHaveAttribute('data-theme', theme)
  })

  it('leaves the page to follow the device when nothing is stored', () => {
    run()

    expect(html).not.toHaveAttribute('data-theme')
  })

  it.each(['system', '', 'Dark', 'sepia'])('leaves the page to follow the device when %j is stored', (value) => {
    localStorage.setItem(KEY, value)

    run()

    expect(html).not.toHaveAttribute('data-theme')
  })

  it('does not throw when storage is blocked, and leaves the page to follow the device', () => {
    localStorage.setItem(KEY, 'dark')
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })

    expect(run).not.toThrow()
    expect(html).not.toHaveAttribute('data-theme')
  })

  it('is loaded by index.html in its head, as a classic script that runs at once', async () => {
    const { default: page } = await import('../index.html?raw')
    const tag = new DOMParser().parseFromString(page, 'text/html').head.querySelector('script[src="/theme-init.js"]')

    expect(tag).not.toBeNull()
    // A module, or a deferred or async script, would run after the page is first drawn.
    expect(['type', 'defer', 'async'].filter((name) => tag!.hasAttribute(name))).toEqual([])
  })
})
