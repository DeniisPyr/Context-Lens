import { useCallback, useSyncExternalStore } from 'react'

// Whether the window matches a media query, such as '(max-width: 1279px)', kept up to date as the window changes size.
// False where there's no matchMedia, as in jsdom, which applies no media queries either.
export function useMediaQuery(query: string) {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia?.(query)
      list?.addEventListener('change', onChange)
      return () => list?.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => window.matchMedia?.(query).matches ?? false)
}
