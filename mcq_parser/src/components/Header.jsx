import React, { useState, useRef, useEffect } from 'react'
import { useBookSearch } from '../hooks/useBookSearch'

export default function Header({ 
    bookTitle, 
    edition, 
    onSearchSelect, 
    showHighlights, 
    setShowHighlights,
    showPDF,
    setShowPDF,
    isBookmarkActive,
    toggleBookmark,
    bookId
}) {
  const { search, loadIndex, loading } = useBookSearch(bookId)
  const [query, setQuery] = useState('')
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || 'light')
  const searchRef = useRef(null)

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(newTheme)
    document.documentElement.dataset.theme = newTheme
  }

  const results = search(query)

  // Close search on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setIsSearchOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <header className="header" style={{
        gridColumn: '1 / -1',
        display: 'grid',
        gridTemplateColumns: '240px 1fr 280px',
        alignItems: 'center',
        background: 'var(--bg-surface)',
        borderBottom: '1px solid var(--border)',
        height: '48px',
        padding: '0',
        zIndex: 100
    }}>
      {/* Col 1: Logo/Title */}
      <div style={{ padding: '0 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{ 
            width: '8px', height: '8px', background: '#10B981', borderRadius: '50%' 
        }} />
        <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>MedViewer</span>
      </div>

      {/* Col 2: Search & Center Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', height: '100%', padding: '0 16px' }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: '400px' }} ref={searchRef}>
          <input 
            type="text" 
            placeholder="Search book..." 
            value={query}
            onFocus={() => {
                loadIndex()
                setIsSearchOpen(true)
            }}
            onChange={(e) => {
                setQuery(e.target.value)
                setIsSearchOpen(true)
            }}
            onKeyDown={(e) => e.key === 'Escape' && setIsSearchOpen(false)}
            style={{
                width: '100%',
                background: 'var(--bg-base)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '6px 12px',
                fontSize: '13px',
                color: 'var(--text-primary)',
                outline: 'none'
            }}
          />
          {isSearchOpen && (query.length >= 2 || loading) && (
            <div style={{
                position: 'absolute',
                top: 'calc(100% + 4px)',
                left: 0,
                right: 0,
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)',
                maxHeight: '400px',
                overflowY: 'auto',
                zIndex: 1000,
                padding: '4px'
            }}>
              {loading ? (
                <div style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>Loading search index...</div>
              ) : results.length > 0 ? (
                results.map((res) => (
                    <div 
                        key={res.item.blockId} 
                        onClick={() => {
                            onSearchSelect(res.item.blockId)
                            setIsSearchOpen(false)
                        }}
                        style={{
                            padding: '10px 12px',
                            cursor: 'pointer',
                            borderRadius: '6px',
                            transition: 'background 0.2s'
                        }}
                        className="search-result-item"
                    >
                        <div style={{ fontSize: '10px', color: '#2563EB', fontWeight: 600, textTransform: 'uppercase', marginBottom: '2px' }}>
                            {res.item.chapterTitle} • {res.item.sectionTitle}
                        </div>
                        <div style={{ fontSize: '13px', color: 'var(--text-primary)', lineHeight: '1.4' }}
                             dangerouslySetInnerHTML={{ 
                                 __html: res.item.text.length > 120 ? res.item.text.slice(0, 120) + '...' : res.item.text 
                             }} 
                        />
                    </div>
                ))
              ) : (
                <div style={{ padding: '12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>No results found</div>
              )}
            </div>
          )}
        </div>

        <div style={{ borderLeft: '1px solid var(--border)', height: '24px', margin: '0 8px' }} />

        <button 
            onClick={() => setShowHighlights(!showHighlights)}
            style={{
                background: showHighlights ? 'var(--accent-glow)' : 'transparent',
                border: '1px solid var(--border)',
                color: showHighlights ? 'var(--accent)' : 'var(--text-secondary)',
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '12px',
                cursor: 'pointer'
            }}
        >
            Highlights
        </button>

        <button 
            onClick={() => setShowPDF(!showPDF)}
            style={{
                background: showPDF ? 'var(--accent-glow)' : 'transparent',
                border: '1px solid var(--border)',
                color: showPDF ? 'var(--accent)' : 'var(--text-secondary)',
                padding: '4px 10px',
                borderRadius: '6px',
                fontSize: '12px',
                cursor: 'pointer'
            }}
        >
            View PDF
        </button>
      </div>

      {/* Col 3: Book Metadata & App Controls */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px', padding: '0 12px' }}>
        <div style={{ textAlign: 'right', overflow: 'hidden' }}>
            <div style={{ 
                fontSize: '12px', 
                fontWeight: 600, 
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '180px'
            }} title={bookTitle}>
                {bookTitle}
            </div>
            {edition && <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{edition} Edition</div>}
        </div>

        <button 
            onClick={toggleTheme}
            style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                fontSize: '16px',
                cursor: 'pointer',
                padding: '4px'
            }}
            title="Toggle Dark Mode"
        >
            {theme === 'light' ? '🌙' : '☀️'}
        </button>
      </div>
      
      <style>{`
        .search-result-item:hover { background: var(--bg-hover); }
        .search-result-item mark { background: #FEF3C7; color: #111827; padding: 0 2px; border-radius: 2px; font-weight: 500; }
      `}</style>
    </header>
  )
}
