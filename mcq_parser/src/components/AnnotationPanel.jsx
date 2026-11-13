import React, { useState } from 'react'

export default function AnnotationPanel({ 
    annotations, 
    onDeleteHighlight, 
    onDeleteNote, 
    onDeleteBookmark, 
    onJumpToBlock,
    bookId,
    currentSelection,
    onAddNote
}) {
  const [activeTab, setActiveTab] = useState('highlights')
  const [noteText, setNoteText] = useState('')

  const formatDate = (isoString) => {
    const date = new Date(isoString)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <aside className="annotation-panel" style={{
        background: 'var(--bg-surface)',
        borderLeft: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden'
    }}>
      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}>
        {['highlights', 'notes', 'bookmarks'].map(tab => (
            <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                    flex: 1,
                    padding: '12px 0',
                    fontSize: '11px',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    background: activeTab === tab ? 'transparent' : 'var(--bg-base)',
                    color: activeTab === tab ? 'var(--accent)' : 'var(--text-muted)',
                    border: 'none',
                    borderBottom: activeTab === tab ? '2px solid var(--accent)' : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                }}
            >
                {tab}
            </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
        {activeTab === 'highlights' && (
            <div>
                {annotations.highlights.length === 0 ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                        No highlights yet. Select text in the reader to highlight.
                    </div>
                ) : (
                    annotations.highlights.map(hl => (
                        <div 
                            key={hl.id} 
                            style={{ 
                                background: 'var(--bg-base)', 
                                border: '1px solid var(--border)', 
                                borderRadius: '8px', 
                                padding: '12px', 
                                marginBottom: '12px',
                                position: 'relative'
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                                <div style={{ width: '8px', height: '8px', background: hl.color, borderRadius: '50%' }} />
                                <span style={{ fontSize: '10px', color: 'var(--text-muted)', fontWeight: 600 }}>{hl.colorLabel}</span>
                                <button 
                                    onClick={() => onDeleteHighlight(hl.id)}
                                    style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#EF4444', fontSize: '14px', cursor: 'pointer' }}
                                >×</button>
                            </div>
                            <div 
                                onClick={() => onJumpToBlock(hl.blockId)}
                                style={{ fontSize: '13px', color: 'var(--text-primary)', fontStyle: 'italic', cursor: 'pointer', lineHeight: '1.4' }}
                            >
                                "{hl.text}"
                            </div>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '8px' }}>{formatDate(hl.createdAt)}</div>
                        </div>
                    ))
                )}
            </div>
        )}

        {activeTab === 'notes' && (
            <div>
                {annotations.notes.length === 0 ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                        No notes yet. Add notes to your highlights or selections.
                    </div>
                ) : (
                    annotations.notes.map(note => (
                        <div 
                            key={note.id} 
                            style={{ 
                                background: 'var(--bg-base)', 
                                border: '1px solid var(--border)', 
                                borderRadius: '8px', 
                                padding: '12px', 
                                marginBottom: '12px'
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                <span style={{ fontSize: '10px', color: '#2563EB', fontWeight: 600 }}>NOTE ANCHOR</span>
                                <button 
                                    onClick={() => onDeleteNote(note.id)}
                                    style={{ background: 'none', border: 'none', color: '#EF4444', fontSize: '14px', cursor: 'pointer' }}
                                >×</button>
                            </div>
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', borderLeft: '2px solid var(--border)', paddingLeft: '8px', marginBottom: '8px' }}>
                                "{note.text}"
                            </div>
                            <div style={{ fontSize: '13px', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                                {note.note}
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '12px', alignItems: 'center' }}>
                                <button 
                                    onClick={() => onJumpToBlock(note.blockId)}
                                    style={{ fontSize: '11px', color: '#2563EB', background: 'none', border: 'none', cursor: 'pointer' }}
                                >Jump to block</button>
                                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{formatDate(note.createdAt)}</span>
                            </div>
                        </div>
                    ))
                )}
            </div>
        )}

        {activeTab === 'bookmarks' && (
            <div>
                {annotations.bookmarks.length === 0 ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                        No bookmarks.
                    </div>
                ) : (
                    annotations.bookmarks.map(bm => (
                        <div 
                            key={bm.blockId} 
                            onClick={() => onJumpToBlock(bm.blockId)}
                            style={{ 
                                background: 'var(--bg-base)', 
                                border: '1px solid var(--border)', 
                                borderRadius: '8px', 
                                padding: '12px', 
                                marginBottom: '12px',
                                cursor: 'pointer'
                            }}
                        >
                            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                                🔖 {bm.sectionTitle}
                            </div>
                            <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                                {bm.chapterTitle}
                            </div>
                            <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '8px' }}>
                                Added on {formatDate(bm.createdAt)}
                            </div>
                        </div>
                    ))
                )}
            </div>
        )}
      </div>

      {/* Note Input at Bottom */}
      <div style={{ 
          padding: '16px', 
          borderTop: '1px solid var(--border)', 
          background: 'var(--bg-base)',
          opacity: currentSelection ? 1 : 0.6,
          pointerEvents: currentSelection ? 'auto' : 'none'
      }}>
        <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
            {currentSelection ? 'Add note to selection' : 'Select text to add note'}
        </div>
        {currentSelection && (
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontStyle: 'italic', marginBottom: '8px', borderLeft: '2px solid var(--accent)', paddingLeft: '8px' }}>
                "{currentSelection.text.length > 60 ? currentSelection.text.slice(0, 60) + '...' : currentSelection.text}"
            </div>
        )}
        <textarea 
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder={currentSelection ? "Enter your note..." : "Please select text in the reader first."}
            style={{
                width: '100%',
                height: '80px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '10px',
                fontSize: '13px',
                color: 'var(--text-primary)',
                resize: 'none',
                outline: 'none',
                marginBottom: '10px'
            }}
        />
        <button 
            disabled={!currentSelection || !noteText.trim()}
            onClick={() => {
                onAddNote(noteText)
                setNoteText('')
                setActiveTab('notes')
            }}
            style={{
                width: '100%',
                background: currentSelection && noteText.trim() ? 'var(--accent)' : 'var(--bg-elevated)',
                color: currentSelection && noteText.trim() ? '#FFF' : 'var(--text-muted)',
                border: 'none',
                padding: '8px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: currentSelection && noteText.trim() ? 'pointer' : 'default',
                transition: 'all 0.2s'
            }}
        >
            Save Note
        </button>
      </div>
    </aside>
  )
}
