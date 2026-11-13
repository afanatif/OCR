export const progressService = {
  save: (bookId, readBlocks) => {
    localStorage.setItem(`progress_${bookId}`, JSON.stringify([...readBlocks]))
  },

  load: (bookId) => {
    const raw = localStorage.getItem(`progress_${bookId}`)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  },

  saveLastBlock: (bookId, blockId) => {
    localStorage.setItem(`lastBlock_${bookId}`, blockId)
  },

  loadLastBlock: (bookId) => {
    return localStorage.getItem(`lastBlock_${bookId}`) || null
  },
}
