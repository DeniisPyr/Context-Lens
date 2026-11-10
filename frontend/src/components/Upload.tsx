import { type ChangeEvent, type DragEvent, type RefObject, useId, useState } from 'react'
import { uploadDocument } from '../api/documents.ts'
import { CheckCircleIcon, PendingIcon, SpinnerIcon, UploadIcon, XCircleIcon, XIcon } from './icons.tsx'

type Props = {
  datasetId: string
  busy: boolean
  // The file input, which Workspace focuses when the empty questions column asks for files.
  inputRef: RefObject<HTMLInputElement | null>
  onBusyChange: (busy: boolean) => void
  onUploaded: () => void
}

// Where a file of the run is: finished one way or the other, being sent, or waiting for the ones before it.
type FileState = 'uploaded' | 'failed' | 'uploading' | 'waiting'

const STATE_ICONS = {
  uploaded: <CheckCircleIcon className="icon-sm" />,
  failed: <XCircleIcon className="icon-sm" />,
  uploading: <SpinnerIcon className="icon-sm spinner" />,
  waiting: <PendingIcon className="icon-sm" />,
}

// A failed file shows its error instead.
const STATE_TEXTS = { uploaded: 'Uploaded', uploading: 'Uploading…', waiting: 'Waiting' }

// The drop zone, and under it a card that follows the files of the last run. Choosing or dropping files starts the
// run at once: there's nothing more to confirm.
export default function Upload({ datasetId, busy, inputRef, onBusyChange, onUploaded }: Props) {
  // The names of the files in the last run, in order, and one result for each file that has finished: its error, or
  // null when it was uploaded. The run is on until every file has its result.
  const [filenames, setFilenames] = useState<string[]>([])
  const [results, setResults] = useState<(string | null)[]>([])
  const [dragging, setDragging] = useState(false)
  const hintId = useId()
  const progressId = useId()

  const running = results.length < filenames.length
  const failed = results.filter((failure) => failure !== null).length

  // One file at a time, in the order given, into the dataset this was rendered for: the page is busy until the run
  // ends, so nobody can select another one meanwhile.
  async function uploadAll(files: File[]) {
    setFilenames(files.map((file) => file.name))
    setResults([])
    onBusyChange(true)
    try {
      for (const file of files) {
        let failure: string | null = null
        try {
          await uploadDocument(datasetId, file)
          onUploaded()
        } catch (err) {
          failure = (err as Error).message
        }
        setResults((current) => [...current, failure])
      }
    } finally {
      onBusyChange(false)
    }
  }

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    // A copy, because emptying the input next also empties its list of files. Emptying it means the same files can
    // be chosen again. A chooser closed with nothing chosen starts nothing, and the last run's results stay.
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length > 0) await uploadAll(files)
  }

  // Without preventDefault the browser would refuse the drop, or open the file in place of the app, so it's
  // called even while busy, when the drop is only turned away.
  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    event.dataTransfer.dropEffect = busy ? 'none' : 'copy'
    if (!busy) setDragging(true)
  }

  // Moving onto a child of the zone also leaves the zone itself, so only leaving it for somewhere outside counts.
  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
  }

  async function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    setDragging(false)
    const files = Array.from(event.dataTransfer.files)
    if (!busy && files.length > 0) await uploadAll(files)
  }

  // Hides the card. The status empties with it, but stays on the page to announce the next run.
  function handleClear() {
    setFilenames([])
    setResults([])
  }

  function stateOf(index: number): FileState {
    if (index < results.length) return results[index] === null ? 'uploaded' : 'failed'
    return index === results.length ? 'uploading' : 'waiting'
  }

  return (
    <>
      <label
        className={['dropzone', dragging && 'dragging', busy && 'disabled'].filter(Boolean).join(' ')}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <span className="dropzone-icon" aria-hidden="true">
          <UploadIcon />
        </span>
        <span className="dropzone-text">
          <strong>Add files</strong> or drop them here
          <span className="dropzone-hint" id={hintId}>
            .txt, .md, .pdf · up to 1&nbsp;MB each
          </span>
        </span>
        <input
          ref={inputRef}
          type="file"
          className="visually-hidden"
          multiple
          accept=".txt,.md,.pdf"
          aria-label="Add files"
          aria-describedby={hintId}
          disabled={busy}
          onChange={handleChange}
        />
      </label>
      <div className={filenames.length > 0 ? 'upload-card' : 'upload-card empty'}>
        <div className="upload-head">
          {filenames.length > 0 &&
            (running ? (
              <UploadIcon className="icon-sm upload-head-icon" />
            ) : failed > 0 ? (
              <XCircleIcon className="icon-sm upload-head-icon failed" />
            ) : (
              <CheckCircleIcon className="icon-sm upload-head-icon uploaded" />
            ))}
          {running && (
            <span id={progressId} className="upload-progress">
              Uploading {results.length + 1} of {filenames.length}…
            </span>
          )}
          {/* Always on the page, because a screen reader only announces a change to a status it already knows about.
              It says one thing per run, and the rows are plain text, so a long run isn't a burst of announcements. */}
          <p className="upload-summary" role="status">
            {!running && results.length > 0 && `${results.length - failed} uploaded, ${failed} failed.`}
          </p>
          {filenames.length > 0 && !running && (
            <button type="button" className="icon-button" aria-label="Clear upload results" onClick={handleClear}>
              <XIcon className="icon-sm" />
            </button>
          )}
        </div>
        {running && (
          <progress className="upload-bar" max={filenames.length} value={results.length} aria-labelledby={progressId} />
        )}
        {filenames.length > 0 && (
          <ul className="upload-results" aria-label="Upload results">
            {/* By position: two files in a run can have the same name, and the list never reorders. */}
            {filenames.map((filename, index) => {
              const state = stateOf(index)
              return (
                <li key={index} className={`upload-row ${state}`}>
                  {STATE_ICONS[state]}
                  <span className="upload-file" title={filename}>
                    {filename}
                  </span>
                  <span className="upload-state">
                    {state === 'failed' ? results[index] : STATE_TEXTS[state]}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </>
  )
}
