import { useState, useEffect } from 'react'

export function useHighlights(bookId) {
  const [highlights, setHighlights] = useState([])

  // Load highlights for the specific book on mount/change
  useEffect(() => {
    if (!bookId) return
    
    try {
      const stored = localStorage.getItem(`highlights_${bookId}`)
      if (stored) setHighlights(JSON.parse(stored))
      else setHighlights([])
    } catch (e) {
      console.error('Failed to load highlights from localStorage', e)
    }
  }, [bookId])

  const addHighlight = (page, text, color = 'rgba(255, 214, 0, 0.4)') => {
    if (!bookId || !text.trim()) return

    const newHighlight = { id: crypto.randomUUID(), page, text, color, timestamp: Date.now() }
    const updated = [...highlights, newHighlight]
    
    setHighlights(updated)
    localStorage.setItem(`highlights_${bookId}`, JSON.stringify(updated))
  }

  const removeHighlight = (id) => {
    if (!bookId) return
    const updated = highlights.filter(h => h.id !== id)
    setHighlights(updated)
    localStorage.setItem(`highlights_${bookId}`, JSON.stringify(updated))
  }

  return { highlights, addHighlight, removeHighlight }
}
