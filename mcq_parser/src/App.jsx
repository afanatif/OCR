import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { bookService } from './services/bookService'
import { annotationService } from './services/annotationService'
import { progressService } from './services/progressService'

import Header from './components/Header'
import TOCSidebar from './components/TOCSidebar'
import TextPanel from './components/TextPanel'
import AnnotationPanel from './components/AnnotationPanel'
import PDFViewer from './components/PDFViewer'
import LibraryBrowser from './components/LibraryBrowser'

// Build a map of "Figure X.Y" / "Table X.Y" -> { blockId, page }
function buildReferenceIndex(bookData) {
  const index = {}
  if (!bookData?.chapters) return index

  const addRef = (key, blockId, page) => {
    const norm = key.trim().toLowerCase().replace(/\s+/g, ' ')
    if (!index[norm]) index[norm] = { blockId, page }
  }

  for (const ch of bookData.chapters) {
    for (const sec of ch.sections || []) {
      for (const block of sec.blocks || []) {
        const page = block.page || null
        // Tables have caption like "Table 1.1: ..."
        if (block.type === 'table' && block.caption) {
          const m = block.caption.match(/^(Table\s+\d+[\.\-]\d+)/i)
          if (m) addRef(m[1], block.id, page)
        }
        // Images have caption like "Figure 1.1: ..."
        if (block.type === 'image' && block.caption) {
          const m = block.caption.match(/^(Fig(?:ure)?\s+\d+[\.\-]\d+)/i)
          if (m) {
            addRef(m[1], block.id, page)
            // Also add normalized "Figure X.Y" form for "Fig X.Y"
            const num = m[1].match(/\d+[\.\-]\d+/)[0]
            addRef(`Figure ${num}`, block.id, page)
            addRef(`Fig ${num}`, block.id, page)
            addRef(`Fig. ${num}`, block.id, page)
          }
        }
      }
    }
  }
  return index
}

export default function App() {
  const [library, setLibrary] = useState([])
  const [selectedBookId, setSelectedBookId] = useState(null)
  const [currentSelection, setCurrentSelection] = useState(null)
  
  const [bookData, setBookData] = useState(null)
  const [currentChapter, setCurrentChapter] = useState(null)
  const [loading, setLoading] = useState(false)
  
  const referenceIndex = useMemo(() => {
    const idx = buildReferenceIndex(bookData)
    console.log('[RefIndex] built', Object.keys(idx).length, 'refs. Sample:', Object.keys(idx).slice(0, 10))
    return idx
  }, [bookData])

  const [annotations, setAnnotations] = useState({ highlights: [], notes: [], bookmarks: [] })
  const [readBlocks, setReadBlocks] = useState(new Set())
  const [showHighlights, setShowHighlights] = useState(true)
  const [showPDF, setShowPDF] = useState(false)
  const [activeBlockId, setActiveBlockId] = useState(null)

  // Define scrollToBlock - can be called with or without data
  const scrollToBlock = useCallback((blockId) => {
    if (!blockId || !bookData) {
        return
    }
    
    // Find which chapter this block belongs to
    let targetCh = null
    const sectionIdPrefix = blockId.split('_b')[0]
    
    for (const ch of bookData.chapters) {
        const found = ch.sections.some(s => s.id === sectionIdPrefix || s.blocks.some(b => b.id === blockId))
        if (found) {
            targetCh = ch
            break
        }
    }

    if (targetCh) {
        setCurrentChapter(targetCh)
        setActiveBlockId(blockId)
        progressService.saveLastBlock(selectedBookId, blockId)
        
        // Wait for render then scroll and flash
        setTimeout(() => {
            const el = document.getElementById(blockId)
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'start' })
                el.classList.remove('ref-target-flash')
                // Force reflow to restart animation
                void el.offsetWidth
                el.classList.add('ref-target-flash')
                setTimeout(() => el.classList.remove('ref-target-flash'), 2000)
            }
        }, 100)
    }
  }, [bookData, selectedBookId])

  // 1. Load library on mount
  useEffect(() => {
    bookService.getLibrary()
      .then(setLibrary)
      .catch(err => console.error("Failed to load library:", err))
  }, [])

  // 2. Load book metadata when selection changes
  useEffect(() => {
    if (!selectedBookId) {
        setBookData(null)
        setCurrentChapter(null)
        return
    }

    setLoading(true)
    bookService.getBook(selectedBookId)
      .then(data => {
        console.log('Book loaded:', { 
          bookId: selectedBookId, 
          chapters: data.chapters?.length,
          hasSections: data.chapters?.[0]?.sections?.length > 0
        })
        
        if (!data.chapters || data.chapters.length === 0) {
            throw new Error('No chapters found in book data')
        }
        
        setBookData(data)
        // Load annotations & progress
        setAnnotations(annotationService.getAll(selectedBookId))
        setReadBlocks(progressService.load(selectedBookId))
        
        // Pick first chapter by default (restore position in separate effect)
        if (data.chapters.length > 0) {
            setCurrentChapter(data.chapters[0])
        }
      })
      .catch(err => {
        console.error("Failed to load book:", err)
        alert(`Error loading book: ${err.message}`)
      })
      .finally(() => setLoading(false))
  }, [selectedBookId])

  // 3. Coordinate annotation saving
  const handleAddHighlight = (hl) => {
    setAnnotations(prev => ({ ...prev, highlights: [...prev.highlights, hl] }))
    annotationService.saveHighlight(selectedBookId, hl)
  }

  const handleDeleteHighlight = (id) => {
    setAnnotations(prev => ({ ...prev, highlights: prev.highlights.filter(h => h.id !== id) }))
    annotationService.deleteHighlight(selectedBookId, id)
  }

  const handleAddNote = (text) => {
    if (!currentSelection) return
    const note = {
        ...currentSelection,
        note: text,
        id: crypto.randomUUID(),
        createdAt: new Date().toISOString()
    }
    setAnnotations(prev => ({ ...prev, notes: [...prev.notes, note] }))
    annotationService.saveNote(selectedBookId, note)
    setCurrentSelection(null)
  }

  const handleDeleteNote = (id) => {
    setAnnotations(prev => ({ ...prev, notes: prev.notes.filter(n => n.id !== id) }))
    annotationService.deleteNote(selectedBookId, id)
  }

  // 4. Persistence for progress
  useEffect(() => {
    if (selectedBookId && readBlocks.size > 0) {
        progressService.save(selectedBookId, readBlocks)
    }
  }, [readBlocks, selectedBookId])

  // 5. Restore last read position after bookData loads
  useEffect(() => {
    if (!bookData || !selectedBookId) return
    
    const lastBlockId = progressService.loadLastBlock(selectedBookId)
    if (!lastBlockId) return
    
    // Find which chapter this block belongs to
    let targetCh = null
    const sectionIdPrefix = lastBlockId.split('_b')[0]
    
    for (const ch of bookData.chapters) {
        const found = ch.sections.some(s => s.id === sectionIdPrefix || s.blocks.some(b => b.id === lastBlockId))
        if (found) {
            targetCh = ch
            break
        }
    }

    if (targetCh) {
        setCurrentChapter(targetCh)
        setActiveBlockId(lastBlockId)
        
        // Wait for render then scroll
        setTimeout(() => {
            const el = document.getElementById(lastBlockId)
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 100)
    }
  }, [bookData, selectedBookId])

  // Default UI is the "medical reader" (parsed JSON text + TOC + annotations).
  // The old page-image spread viewer was experimental and required a separate manifest/pages pipeline.
  const spreadMode = new URLSearchParams(window.location.search).get('spread') === '1'
  if (spreadMode) {
    return (
      <div style={{ padding: 24, color: 'var(--text-primary)' }}>
        <h2 style={{ marginBottom: 8 }}>Spread viewer removed</h2>
        <p style={{ color: 'var(--text-muted)' }}>
          This project now defaults to the parsed-book reader. Remove <code>?spread=1</code> from the URL.
        </p>
      </div>
    )
  }

  if (!selectedBookId) {
    return <LibraryBrowser library={library} onSelectBook={setSelectedBookId} />
  }

  if (loading || !bookData) {
    return (
        <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg-base)', color: 'var(--text-secondary)' }}>
            Loading {library.find(b => b.id === selectedBookId)?.title || 'Book'}...
        </div>
    )
  }

  const totalBlocks = bookData.chapters.reduce((acc, ch) => 
    acc + ch.sections.reduce((sAcc, s) => sAcc + s.blocks.length, 0), 0
  )

  const selectedBookMeta = library.find(b => b.id === selectedBookId)

  return (
    <div className="app">
      <Header 
        bookTitle={bookData.metadata.title}
        edition={bookData.metadata.edition}
        bookId={selectedBookId}
        onSearchSelect={scrollToBlock}
        showHighlights={showHighlights}
        setShowHighlights={setShowHighlights}
        showPDF={showPDF}
        setShowPDF={setShowPDF}
        onHome={() => setSelectedBookId(null)}
      />

      <TOCSidebar 
        chapters={bookData.chapters}
        activeBlockId={activeBlockId}
        onBlockSelect={scrollToBlock}
        readBlocks={readBlocks}
        totalBlocks={totalBlocks}
        bookmarks={annotations.bookmarks}
      />

      <div style={{ 
          display: 'flex', 
          height: '100%', 
          overflow: 'hidden',
          gridColumn: showPDF ? '2 / 3' : '2 / 3' // Header takes 1 / -1, so 2 is reader center
      }}>
          <div style={{ flex: showPDF ? 0.5 : 1, transition: 'flex 0.3s ease' }}>
            <TextPanel 
                blocks={currentChapter?.sections.flatMap(s => s.blocks) || []}
                annotations={annotations}
                onAddHighlight={handleAddHighlight}
                onSelectionChange={setCurrentSelection}
                setReadBlocks={setReadBlocks}
                activeChapterId={currentChapter?.id}
                referenceIndex={referenceIndex}
                onRefClick={scrollToBlock}
            />
          </div>
          
          {showPDF && (
            <div style={{ flex: 0.5, borderLeft: '1px solid var(--border)' }}>
              <PDFViewer 
                pdfUrl={selectedBookMeta?.pdfPath}
                show={showPDF}
              />
            </div>
          )}
      </div>

      <AnnotationPanel 
        annotations={annotations}
        onDeleteHighlight={handleDeleteHighlight}
        onDeleteNote={handleDeleteNote}
        onJumpToBlock={scrollToBlock}
        bookId={selectedBookId}
        currentSelection={currentSelection}
        onAddNote={handleAddNote}
      />

      <button 
        onClick={() => setSelectedBookId(null)}
        style={{
            position: 'fixed',
            bottom: '24px',
            left: '24px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            padding: '8px 16px',
            borderRadius: '20px',
            fontSize: '12px',
            cursor: 'pointer',
            boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
            zIndex: 1000
        }}
      >
          🏠 Library
      </button>
    </div>
  )
}
