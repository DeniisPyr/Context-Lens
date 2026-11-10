import { useId, useState } from 'react'
import { applyTheme, readTheme, saveTheme, type Theme } from '../theme.ts'
import { MonitorIcon, MoonIcon, SunIcon } from './icons.tsx'

const OPTIONS = [
  { theme: 'system', label: 'System', Icon: MonitorIcon },
  { theme: 'light', label: 'Light', Icon: SunIcon },
  { theme: 'dark', label: 'Dark', Icon: MoonIcon },
] as const

// Real radio buttons, drawn as one segmented control: the arrow keys move between them, and a screen reader says
// which of the three is chosen.
export default function ThemeSwitch() {
  // main.tsx has already applied the stored choice, so this only needs to know which one it was.
  const [theme, setTheme] = useState<Theme>(readTheme)
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
