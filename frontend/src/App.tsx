import ApiStatus from './components/ApiStatus.tsx'
import Ask from './components/Ask.tsx'
import Documents from './components/Documents.tsx'
import { useDocuments } from './hooks/useDocuments.ts'

export default function App() {
  const { documents, error, reload } = useDocuments()

  return (
    <main>
      <h1>Context-Lens</h1>
      <p>Ask questions about your documents and get answers you can check.</p>
      <ApiStatus />
      <Documents documents={documents} error={error} onUploaded={reload} />
      <Ask documents={documents} />
    </main>
  )
}
