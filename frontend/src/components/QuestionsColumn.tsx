import type { Dataset } from '../api/datasets.ts'
import Ask from './Ask.tsx'
import { InfoIcon, StackIcon } from './icons.tsx'

type Props = {
  // undefined while the datasets load, or when there are none.
  dataset: Dataset | undefined
  // True once the list has loaded and is empty, so the start prompt can't show before we know.
  noDatasets: boolean
  // Also false while the list is still loading, so the form only shows once there's something to search.
  hasDocuments: boolean
}

// The middle of the page: a header naming the dataset, and below it, scrolling on its own, the questions about it.
export default function QuestionsColumn({ dataset, noDatasets, hasDocuments }: Props) {
  return (
    <main className="questions">
      <header className="questions-header">
        <div className="questions-title">
          {dataset && (
            <p className="crumb">
              <StackIcon className="icon-sm" />
              <span className="crumb-name">{dataset.name}</span>
            </p>
          )}
          <h2>Questions in this session</h2>
        </div>
        <p className="questions-note">
          <InfoIcon className="icon-sm" />
          Each question is answered on its own. Earlier ones aren&rsquo;t remembered.
        </p>
      </header>
      <div className="questions-body">
        {noDatasets && <p className="empty-state">Create a dataset to get started.</p>}
        {/* Keyed by the dataset, so switching starts it over: the old question and answer can't show under the new
            dataset, and nothing resets them. */}
        {dataset && (
          <Ask key={dataset.id} datasetId={dataset.id} datasetName={dataset.name} hasDocuments={hasDocuments} />
        )}
      </div>
    </main>
  )
}
