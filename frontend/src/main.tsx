import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyTheme, readTheme } from './theme.ts'

// public/theme-init.js, which index.html loads before anything is drawn, has applied the stored theme already. This
// applies it again in case that script couldn't load: the page then switches to the stored theme a moment late
// rather than not at all, and the theme switch, which starts on the theme the page shows, shows the stored choice.
applyTheme(readTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
