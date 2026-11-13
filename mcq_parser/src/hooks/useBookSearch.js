import Fuse from 'fuse.js'
import { useState, useMemo, useCallback } from 'react'
import { bookService } from '../services/bookService'

export function useBookSearch(bookId) {
  const [index, setIndex] = useState(null)
  const [loading, setLoading] = useState(false)

  const loadIndex = useCallback(async () => {
    if (index || loading || !bookId) return
    setLoading(true)
    try {
        const data = await bookService.getSearchIndex(bookId)
        setIndex(data)
    } catch (err) {
        console.error("Search index load failed:", err)
    } finally {
        setLoading(false)
    }
  }, [bookId, index, loading])

  const fuse = useMemo(() =>
    index ? new Fuse(index, {
      keys: ['text', 'chapterTitle', 'sectionTitle'],
      threshold: 0.3,
      includeMatches: true,
      minMatchCharLength: 3
    }) : null,
  [index])

  const search = useCallback((query) => {
    if (!fuse || !query || query.length < 2) return []
    return fuse.search(query).slice(0, 20)
  }, [fuse])

  return { search, loadIndex, loading, hasIndex: !!index }
}
