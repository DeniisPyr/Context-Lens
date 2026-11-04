import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import styles from '../index.css?raw'

// jsdom applies a stylesheet it is given, so tests can check the rules the page depends on.
const style = document.createElement('style')
style.textContent = styles
document.head.append(style)

// jsdom has no layout, so it leaves this out. A test that cares can spy on it.
Element.prototype.scrollIntoView = () => {}

afterEach(() => {
  cleanup()
})
