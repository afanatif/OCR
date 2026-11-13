import { useState, useEffect } from 'react'

export function useLibrary() {
  const [library, setLibrary] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/data/index.json')
      .then(r => {
        if (!r.ok) throw new Error('Library index not found')
        return r.json()
      })
      .then(data => {
        setLibrary(data.books || [])
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return { library, loading, error }
}
