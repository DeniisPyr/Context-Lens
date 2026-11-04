import ApiStatus from './components/ApiStatus.tsx'
import Documents from './components/Documents.tsx'

export default function App() {
  return (
    <main>
      <h1>Context-Lens</h1>
      <p>Ask questions about your documents and get answers you can check.</p>
      <ApiStatus />
      <Documents />
    </main>
  )
}
