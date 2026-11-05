import { type SubmitEvent, useRef, useState } from 'react'
import { uploadDocument } from '../api/documents.ts'

type Props = {
  datasetId: string
  onUploaded: () => void
}

export default function UploadForm({ datasetId, onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const file = input.current?.files?.[0]
    if (!file) {
      setError('Choose a file first.')
      return
    }

    setUploading(true)
    setError(null)
    try {
      await uploadDocument(datasetId, file)
      // Empty the input so the same file can be chosen again.
      if (input.current) input.current.value = ''
      onUploaded()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <label>
        Choose a .txt or .md file
        <input ref={input} type="file" accept=".txt,.md" />
      </label>
      <button type="submit" disabled={uploading}>
        {uploading ? 'Uploading…' : 'Upload'}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}
