import { type RefObject, useId, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { createDataset, type Dataset, deleteDataset } from '../api/datasets.ts'
import ConfirmDelete from './ConfirmDelete.tsx'
import CreateDatasetForm from './CreateDatasetForm.tsx'
import { ChevronsUpDownIcon, PlusIcon, StackIcon, TrashIcon } from './icons.tsx'

type Props = {
  datasets: Dataset[] | null
  error: string | null
  selected: Dataset | undefined
  // How many documents the selected dataset holds, for the line under its name. null while they load.
  documentCount: number | null
  busy: boolean
  // The new dataset's name field, which Workspace focuses when the empty questions column asks for a dataset.
  nameInputRef: RefObject<HTMLInputElement | null>
  onBusyChange: (busy: boolean) => void
  onChoose: (id: string) => void
  onCreated: (dataset: Dataset) => void
  onDeleted: (id: string) => void
}

// The line under the dataset's name, such as "7 documents · 1 of 3 datasets".
function captionOf(datasets: Dataset[], selected: Dataset, documentCount: number | null) {
  const documents = documentCount === null ? null : documentCount === 1 ? '1 document' : `${documentCount} documents`
  const place =
    datasets.length === 1 ? 'the only dataset' : `${datasets.indexOf(selected) + 1} of ${datasets.length} datasets`
  return documents ? `${documents} · ${place}` : place
}

// The top of the sidebar: which dataset is selected, and the buttons that create and delete one.
export default function Datasets({
  datasets,
  error,
  selected,
  documentCount,
  busy,
  nameInputRef: nameInput,
  onBusyChange,
  onChoose,
  onCreated,
  onDeleted,
}: Props) {
  const [formOpen, setFormOpen] = useState(false)
  const newButton = useRef<HTMLButtonElement>(null)
  const selectId = useId()
  const captionId = useId()

  // With no dataset to show, creating one is all there is to do, so the form is open by itself and can't be closed.
  // While the first load runs nothing is known yet, so it waits for the list or its error.
  const formRequired = !selected && (datasets !== null || error !== null)

  // Each of these renders at once with flushSync, so the element that should get the focus is already there.
  function openForm() {
    flushSync(() => setFormOpen(true))
    nameInput.current?.focus()
  }

  function closeForm() {
    flushSync(() => setFormOpen(false))
    newButton.current?.focus()
  }

  // The page is busy meanwhile, so nobody can switch to another dataset, upload or delete one halfway through. Once
  // the dataset is there, the page lets go, selects it and closes the form in one render, so the New dataset button
  // is back and enabled to take the focus.
  async function handleCreate(name: string) {
    onBusyChange(true)
    try {
      const dataset = await createDataset(name)
      flushSync(() => {
        onBusyChange(false)
        onCreated(dataset)
        setFormOpen(false)
      })
      newButton.current?.focus()
    } finally {
      onBusyChange(false)
    }
  }

  // The page is busy meanwhile, so nobody can switch to another dataset, upload or create one halfway through.
  async function handleDelete(dataset: Dataset) {
    onBusyChange(true)
    try {
      await deleteDataset(dataset.id)
      onDeleted(dataset.id)
    } finally {
      onBusyChange(false)
    }
  }

  return (
    <div className="dataset-choice">
      <div className="dataset-row">
        {selected ? (
          <label className="eyebrow" htmlFor={selectId}>
            Dataset
          </label>
        ) : (
          <span className="eyebrow">Dataset</span>
        )}
        {!formRequired && (
          <button
            ref={newButton}
            type="button"
            className="mini-button accent"
            aria-expanded={formOpen}
            disabled={busy}
            onClick={formOpen ? closeForm : openForm}
          >
            <PlusIcon className="icon-sm" />
            New dataset
          </button>
        )}
        {selected && (
          // Keyed by the dataset, so an open question closes when another one is selected, whatever selects it.
          <ConfirmDelete
            key={selected.id}
            label="Delete"
            accessibleLabel="Delete dataset"
            icon={<TrashIcon className="icon-sm" />}
            className="mini-button"
            question={`Delete ${selected.name} and all its documents? This can't be undone.`}
            disabled={busy}
            onConfirm={() => handleDelete(selected)}
          />
        )}
      </div>
      {(formOpen || formRequired) && (
        <CreateDatasetForm
          inputRef={nameInput}
          busy={busy}
          onCreate={handleCreate}
          onCancel={formRequired ? undefined : closeForm}
        />
      )}
      {error && <p role="alert">{error}</p>}
      {selected && datasets && (
        // The real select lies over the whole card, unseen, so a click anywhere on it opens the browser's own list,
        // and the keyboard and screen readers get a plain select. The card only shows what it has chosen.
        <div className="switcher">
          <span className="switcher-icon" aria-hidden="true">
            <StackIcon />
          </span>
          <span className="switcher-text" aria-hidden="true">
            <span className="switcher-name">{selected.name}</span>
            <span className="switcher-caption" id={captionId}>
              {captionOf(datasets, selected, documentCount)}
            </span>
          </span>
          <ChevronsUpDownIcon className="icon-sm switcher-chevrons" />
          <select
            id={selectId}
            className="switcher-select"
            value={selected.id}
            disabled={busy}
            aria-describedby={captionId}
            onChange={(event) => onChoose(event.target.value)}
          >
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
