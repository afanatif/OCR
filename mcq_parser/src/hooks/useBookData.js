import { useState, useEffect } from 'react'

export function useBookData(dataPath) {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    if (!dataPath) return
    
    setLoading(true)
    setError(null)
    setData(null)

    fetch(dataPath)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}: Could not load book data`)
        return r.json()
      })
      .then(json => { 
        setData(json)
        setLoading(false) 
      })
      .catch(err => { 
        setError(err.message)
        setLoading(false) 
      })
  }, [dataPath])

  const getPage = (pageNum) => {
    if (!data) return null
    return data.pages.find(p => p.num === pageNum) || null
  }

  return { data, loading, error, getPage }
}
