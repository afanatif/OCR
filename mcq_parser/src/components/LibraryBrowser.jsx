import React, { useState } from 'react'

export default function LibraryBrowser({ library, onSelectBook }) {
  const [search, setSearch] = useState('')

  const filtered = library.filter(b => b.title.toLowerCase().includes(search.toLowerCase()))

  return (
    <div style={{ 
        padding: '40px', 
        height: '100vh', 
        overflowY: 'auto', 
        background: 'var(--bg-base)',
        color: 'var(--text-primary)'
    }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <header style={{ marginBottom: '40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                  <h1 style={{ fontSize: '28px', marginBottom: '8px' }}>Medical Library</h1>
                  <p style={{ color: 'var(--text-muted)' }}>{library.length} books indexed and ready for review.</p>
              </div>
              <input 
                type="text" 
                placeholder="Search series or book title..." 
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                    padding: '10px 16px',
                    borderRadius: '8px',
                    border: '1px solid var(--border)',
                    background: 'var(--bg-surface)',
                    color: 'var(--text-primary)',
                    width: '300px',
                    outline: 'none'
                }}
              />
          </header>

          <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', 
              gap: '24px' 
          }}>
              {filtered.map(book => {
                  const progress = localStorage.getItem(`progress_${book.id}`)
                  const readCount = progress ? JSON.parse(progress).length : 0
                  // This is a rough estimation since we don't have total blocks here easily
                  // but we can show a simple progress bar if we have the data
                  
                  return (
                      <div 
                        key={book.id} 
                        onClick={() => onSelectBook(book.id)}
                        style={{
                            background: 'var(--bg-surface)',
                            border: '1px solid var(--border)',
                            borderRadius: '12px',
                            padding: '24px',
                            cursor: 'pointer',
                            transition: 'transform 0.2s, border-color 0.2s',
                            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)'
                        }}
                        className="book-card"
                      >
                          <div style={{ 
                              width: '100%', 
                              aspectRatio: '3/4', 
                              background: 'var(--bg-base)', 
                              borderRadius: '6px',
                              marginBottom: '20px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '40px',
                              border: '1px solid var(--border)'
                          }}>
                              📚
                          </div>
                          <h3 style={{ fontSize: '16px', marginBottom: '4px' }}>{book.title}</h3>
                          <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                              <span style={{ fontSize: '10px', background: 'var(--bg-elevated)', padding: '2px 6px', borderRadius: '4px', color: 'var(--text-muted)' }}>
                                  {book.pages} Pages
                              </span>
                              <span style={{ fontSize: '10px', background: 'var(--accent-glow)', padding: '2px 6px', borderRadius: '4px', color: 'var(--accent)' }}>
                                  Ready
                              </span>
                          </div>
                          
                          <div style={{ height: '4px', background: 'var(--border)', borderRadius: '2px', overflow: 'hidden' }}>
                              <div style={{ height: '100%', background: '#10B981', width: '0%' }} title="Reading Progress" />
                          </div>
                      </div>
                  )
              })}
          </div>
      </div>
      <style>{`
        .book-card:hover { transform: translateY(-4px); border-color: var(--accent); }
      `}</style>
    </div>
  )
}
