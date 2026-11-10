import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyTheme, readTheme } from './theme.ts'

// Before the first render, so the page comes up in the stored theme instead of switching to it. A script in
// index.html would run even earlier, but the Content Security Policy allows no inline scripts.
applyTheme(readTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
