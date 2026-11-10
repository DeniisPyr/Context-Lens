import { useId, useState } from 'react'
import { appliedTheme, applyTheme, saveTheme, type Theme } from '../theme.ts'
import { MonitorIcon, MoonIcon, SunIcon } from './icons.tsx'

const OPTIONS = [
  { theme: 'system', label: 'System', Icon: MonitorIcon },
  { theme: 'light', label: 'Light', Icon: SunIcon },
  { theme: 'dark', label: 'Dark', Icon: MoonIcon },
] as const

// Real radio buttons, drawn as one segmented control: the arrow keys move between them, and a screen reader says
// which of the three is chosen.
export default function ThemeSwitch() {
  // Starts on the theme the page shows rather than on what storage says: while storage is blocked, a choice made
  // earlier in this visit, as before logging out and in again, is only on the page.
  const [theme, setTheme] = useState<Theme>(appliedTheme)
  const name = useId()

  function handleChange(chosen: Theme) {
    setTheme(chosen)
    applyTheme(chosen)
    saveTheme(chosen)
  }

  return (
    <fieldset className="theme-switch">
      <legend className="visually-hidden">Theme</legend>
      {OPTIONS.map(({ theme: option, label, Icon }) => (
        <label key={option} className="theme-option">
          <input
            type="radio"
            className="visually-hidden"
            name={name}
            value={option}
            checked={theme === option}
            onChange={() => handleChange(option)}
          />
          <span className="theme-option-face">
            <Icon className="icon-sm" />
            {label}
          </span>
        </label>
      ))}
    </fieldset>
  )
}
