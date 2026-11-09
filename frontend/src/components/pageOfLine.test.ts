import { describe, expect, it } from 'vitest'
import { pageOfLine } from './pageOfLine.ts'

// The page of each line from 1 to lineCount.
const pagesOf = (pageStarts: number[], lineCount: number) =>
  Array.from({ length: lineCount }, (_, index) => pageOfLine(pageStarts, index + 1))

describe('pageOfLine', () => {
  it('finds the page of each line', () => {
    expect(pagesOf([1, 4, 6], 8)).toEqual([1, 1, 1, 2, 2, 3, 3, 3])
  })

  it('puts every line of a single page on page 1', () => {
    expect(pagesOf([1], 3)).toEqual([1, 1, 1])
  })

  it('gives no line to a page with no text', () => {
    // Three pages of 4, 0 and 3 lines.
    expect(pagesOf([1, 5, 5], 7)).toEqual([1, 1, 1, 1, 3, 3, 3])
  })

  it('gives no line to several pages with no text in a row', () => {
    expect(pagesOf([1, 3, 3, 3, 4], 5)).toEqual([1, 1, 4, 5, 5])
  })

  it('gives no line to a first page with no text', () => {
    expect(pagesOf([1, 1, 3], 4)).toEqual([2, 2, 3, 3])
  })

  it('gives no line to a page with no text at the end, which starts after the last line', () => {
    // Pages of 3 and 4 lines, then an empty one.
    expect(pagesOf([1, 4, 8], 7)).toEqual([1, 1, 1, 2, 2, 2, 2])
    expect(pageOfLine([1, 4, 8], 8)).toBe(3)
  })

  it('gives the line after the last to the last page, when several pages at the end have no text', () => {
    expect(pageOfLine([1, 3, 3], 2)).toBe(1)
    expect(pageOfLine([1, 3, 3], 3)).toBe(3)
  })

  it('gives 0 before line 1, where no page has started', () => {
    expect(pageOfLine([1, 4], 0)).toBe(0)
    expect(pageOfLine([1, 1], 0)).toBe(0)
  })
})
