import { useDocuments } from '../hooks/useDocuments.ts'
import Ask from './Ask.tsx'
import Documents from './Documents.tsx'

type Props = {
  datasetId: string
  datasetName: string
  busy: boolean
  onBusyChange: (busy: boolean) => void
}

// Everything that belongs to one dataset. App renders this with the dataset's id as its key, so switching
// starts it over: the old list, question and answer can't show under the new dataset, and nothing resets them.
export default function DatasetContents({ datasetId, datasetName, busy, onBusyChange }: Props) {
  const { documents, error, reload, remove } = useDocuments(datasetId)

  return (
    <>
      <Documents
        datasetId={datasetId}
        documents={documents}
        error={error}
        busy={busy}
        onBusyChange={onBusyChange}
        onUploaded={reload}
        onDeleted={remove}
      />
      <Ask datasetId={datasetId} datasetName={datasetName} hasDocuments={documents !== null && documents.length > 0} />
    </>
  )
}
