import { type SubmitEvent, useRef, useState } from 'react'
import { uploadDocument } from '../api/documents.ts'

type Props = {
  datasetId: string
  busy: boolean
  onBusyChange: (busy: boolean) => void
  onUploaded: () => void
}

// A file that has finished. No failure means it was uploaded.
type FileResult = {
  filename: string
  failure: string | null
}

export default function UploadForm({ datasetId, busy, onBusyChange, onUploaded }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<FileResult[]>([])

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    // A copy, because emptying the input at the end also empties its list of files.
    const files = Array.from(input.current?.files ?? [])
    if (files.length === 0) {
      setError('Choose a file first.')
      return
    }

    setError(null)
    setResults([])
    onBusyChange(true)
    for (const [index, file] of files.entries()) {
      setProgress({ current: index + 1, total: files.length })
      let failure: string | null = null
      try {
        await uploadDocument(datasetId, file)
        onUploaded()
      } catch (err) {
        failure = (err as Error).message
      }
      setResults((current) => [...current, { filename: file.name, failure }])
    }
    setProgress(null)
    // Empty the input so the same files can be chosen again.
    if (input.current) input.current.value = ''
    onBusyChange(false)
  }

  const failed = results.filter((result) => result.failure !== null).length

  return (
    <>
      <form className="upload-form" onSubmit={handleSubmit}>
        <label>
          Choose .txt or .md files
          <input ref={input} type="file" accept=".txt,.md" multiple disabled={busy} />
        </label>
        <button type="submit" disabled={busy}>
          {progress ? `Uploading ${progress.current} of ${progress.total}…` : 'Upload'}
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
      {/* Always on the page, because a screen reader only announces a change to a status it already knows about.
          It says one thing per run, and the rows are plain text, so a long run isn't a burst of announcements. */}
      <p className="upload-summary" role="status">
        {!progress && results.length > 0 && `${results.length - failed} uploaded, ${failed} failed.`}
      </p>
      {results.length > 0 && (
        <ul className="upload-results" aria-label="Upload results">
          {/* By position: two files in a run can have the same name, and rows are only ever added at the end. */}
          {results.map(({ filename, failure }, index) => (
            <li key={index} className={failure === null ? undefined : 'upload-failed'}>
              <span>{filename}</span>
              <span>{failure ?? 'Uploaded'}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
