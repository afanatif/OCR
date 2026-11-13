const key = (bookId) => `annotations_${bookId}`

export const annotationService = {
  getAll: (bookId) => {
    const raw = localStorage.getItem(key(bookId))
    return raw ? JSON.parse(raw) : { highlights: [], notes: [], bookmarks: [] }
  },

  saveHighlight: (bookId, highlight) => {
    const store = annotationService.getAll(bookId)
    // Avoid duplicates
    if (!store.highlights.find(h => h.id === highlight.id)) {
        store.highlights.push(highlight)
        localStorage.setItem(key(bookId), JSON.stringify(store))
    }
  },

  deleteHighlight: (bookId, highlightId) => {
    const store = annotationService.getAll(bookId)
    store.highlights = store.highlights.filter(h => h.id !== highlightId)
    localStorage.setItem(key(bookId), JSON.stringify(store))
  },

  saveNote: (bookId, note) => {
    const store = annotationService.getAll(bookId)
    store.notes.push(note)
    localStorage.setItem(key(bookId), JSON.stringify(store))
  },

  deleteNote: (bookId, noteId) => {
    const store = annotationService.getAll(bookId)
    store.notes = store.notes.filter(n => n.id !== noteId)
    localStorage.setItem(key(bookId), JSON.stringify(store))
  },

  saveBookmark: (bookId, bookmark) => {
    const store = annotationService.getAll(bookId)
    const exists = store.bookmarks.find(b => b.blockId === bookmark.blockId)
    if (!exists) {
        store.bookmarks.push(bookmark)
        localStorage.setItem(key(bookId), JSON.stringify(store))
    }
  },

  removeBookmark: (bookId, blockId) => {
    const store = annotationService.getAll(bookId)
    store.bookmarks = store.bookmarks.filter(b => b.blockId !== blockId)
    localStorage.setItem(key(bookId), JSON.stringify(store))
  },
}
