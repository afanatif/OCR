const BASE = import.meta.env.VITE_API_BASE || '/data'

export const bookService = {
  // Get book metadata + TOC + Chapters
  getBook: (bookId) =>
    fetch(`${BASE}/${bookId}/main.json`)
      .then(r => {
          if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`)
          return r.json()
      })
      .then(data => ({
        metadata: data.metadata,
        toc: data.toc,
        tocHierarchy: data.toc_hierarchy || [],
        chapters: data.chapters || [],
        chapterFiles: data.chapter_files || [],
      })),

  // Get specific chapter data
  getChapter: (bookId, chapterId) =>
    fetch(`${BASE}/${bookId}/${chapterId}.json`)
      .then(r => {
          if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`)
          return r.json()
      })
      .then(data => data.chapter),

  // Search index - lazy loaded (embedded in main.json)
  getSearchIndex: (bookId) =>
    fetch(`${BASE}/${bookId}/main.json`).then(r => {
        if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`)
        return r.json()
    }).then(data => data.search_index || []),

  // Library index
  getLibrary: () =>
    fetch(`${BASE}/index.json`).then(r => {
        if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`)
        return r.json()
    }),
}
