import { useDocuments } from '../hooks/useDocuments.ts'
import Ask from './Ask.tsx'
import Documents from './Documents.tsx'

// Everything that belongs to one dataset. App renders this with the dataset's id as its key, so switching
// starts it over: the old list, question and answer can't show under the new dataset, and nothing resets them.
export default function DatasetContents({ datasetId }: { datasetId: string }) {
  const { documents, error, reload } = useDocuments(datasetId)

  return (
    <>
      <Documents datasetId={datasetId} documents={documents} error={error} onUploaded={reload} />
      <Ask documents={documents} />
    </>
  )
}
