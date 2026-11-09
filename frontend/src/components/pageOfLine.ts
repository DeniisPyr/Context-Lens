// The page of a PDF that holds a line: the last page that starts on it or before it. A page with no text starts where
// the next one does, so it never holds a line. Before line 1, no page has started, so it gives 0.
export function pageOfLine(pageStarts: number[], line: number): number {
  return pageStarts.findLastIndex((start) => start <= line) + 1
}
