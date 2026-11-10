import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ThemeSwitch from './ThemeSwitch.tsx'

const KEY = 'context-lens-theme'
const radio = (name: string) => screen.getByRole('radio', { name })
const html = document.documentElement

afterEach(() => {
  localStorage.clear()
  html.removeAttribute('data-theme')
  vi.restoreAllMocks()
})

describe('ThemeSwitch', () => {
  it('offers System, Light and Dark as radio buttons in a group named Theme', () => {
    render(<ThemeSwitch />)

    const group = screen.getByRole('group', { name: 'Theme' })
    expect(within(group).getAllByRole('radio').map((option) => option.getAttribute('value'))).toEqual([
      'system',
      'light',
      'dark',
    ])
    expect(radio('System')).toBeInTheDocument()
    expect(radio('Light')).toBeInTheDocument()
    expect(radio('Dark')).toBeInTheDocument()
  })

  it('starts on System when the page follows the device', () => {
    render(<ThemeSwitch />)

    expect(radio('System')).toBeChecked()
    expect(radio('Light')).not.toBeChecked()
    expect(radio('Dark')).not.toBeChecked()
  })

  // The stored choice is on the page before the switch shows: theme-init.js and main.tsx apply it.
  it('starts on the theme the page shows', () => {
    localStorage.setItem(KEY, 'dark')
    html.dataset.theme = 'dark'

    render(<ThemeSwitch />)

    expect(radio('Dark')).toBeChecked()
    expect(radio('System')).not.toBeChecked()
  })

  it('starts on the theme the page shows when storage is blocked, as after logging out and in again', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })
    html.dataset.theme = 'light'

    render(<ThemeSwitch />)

    expect(radio('Light')).toBeChecked()
    expect(radio('System')).not.toBeChecked()
  })

  it('switches the page to the theme chosen and stores it', async () => {
    const user = userEvent.setup()
    render(<ThemeSwitch />)

    await user.click(radio('Dark'))

    expect(radio('Dark')).toBeChecked()
    expect(html).toHaveAttribute('data-theme', 'dark')
    expect(localStorage.getItem(KEY)).toBe('dark')

    await user.click(radio('Light'))

    expect(html).toHaveAttribute('data-theme', 'light')
    expect(localStorage.getItem(KEY)).toBe('light')
  })

  it('goes back to following the device on System', async () => {
    const user = userEvent.setup()
    localStorage.setItem(KEY, 'light')
    html.dataset.theme = 'light'
    render(<ThemeSwitch />)

    await user.click(radio('System'))

    expect(radio('System')).toBeChecked()
    expect(html).not.toHaveAttribute('data-theme')
    expect(localStorage.getItem(KEY)).toBe('system')
  })

  it('works from the keyboard: the arrow keys move to the next choice', async () => {
    const user = userEvent.setup()
    render(<ThemeSwitch />)

    await user.tab()
    expect(radio('System')).toHaveFocus()
    await user.keyboard('{ArrowRight}')

    expect(radio('Light')).toBeChecked()
    expect(radio('Light')).toHaveFocus()
    expect(html).toHaveAttribute('data-theme', 'light')
  })

  it('still switches the page when storage is blocked', async () => {
    const user = userEvent.setup()
    const blocked = () => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    }
    localStorage.setItem(KEY, 'light')
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked)
    render(<ThemeSwitch />)

    expect(radio('System')).toBeChecked()
    await user.click(radio('Dark'))

    expect(radio('Dark')).toBeChecked()
    expect(html).toHaveAttribute('data-theme', 'dark')
  })
})
