import React, { useEffect, useRef, useState, useMemo } from 'react'
import TableComponent from './TableComponent'

export default function TextPanel({
    blocks,
    annotations,
    onAddHighlight,
    onSelectionChange,
    setReadBlocks,
    activeChapterId,
    referenceIndex = {},
    onRefClick
}) {
  const [selectionRange, setSelectionRange] = useState(null)
  const [pickerPos, setPickerPos] = useState(null)
  const [selectedText, setSelectedText] = useState('')
  const [twoColumn, setTwoColumn] = useState(() => {
    try { return localStorage.getItem('reader.twoColumn') === '1' } catch { return false }
  })
  const panelRef = useRef(null)

  // Sort blocks into visual reading order: by page, then top-to-bottom, then left-to-right.
  const sortedBlocks = useMemo(() => {
    if (!Array.isArray(blocks)) return []
    const arr = blocks.map((block, index) => ({ block, index }))
    const toQuestionNumber = (value) => {
      if (value == null) return null
      const numeric = Number(String(value).replace(/[^\d.]/g, ''))
      return Number.isFinite(numeric) ? numeric : null
    }

    arr.sort((aItem, bItem) => {
      const a = aItem.block
      const b = bItem.block

      if (a.type === 'mcq' && b.type === 'mcq') {
        const aq = toQuestionNumber(a.qnum)
        const bq = toQuestionNumber(b.qnum)
        if (aq != null && bq != null && aq !== bq) return aq - bq
        if (aq != null && bq == null) return -1
        if (aq == null && bq != null) return 1
      }

      const pa = Number(a.page ?? 0)
      const pb = Number(b.page ?? 0)
      if (pa !== pb) return pa - pb

      const ay = a.bbox && a.bbox[1] != null ? Number(a.bbox[1]) : (a.bbox && a.bbox[3] != null ? Number(a.bbox[3]) : 0)
      const by = b.bbox && b.bbox[1] != null ? Number(b.bbox[1]) : (b.bbox && b.bbox[3] != null ? Number(b.bbox[3]) : 0)
      if (ay !== by) return by - ay // higher y (top) first

      const ax = a.bbox && a.bbox[0] != null ? Number(a.bbox[0]) : 0
      const bx = b.bbox && b.bbox[0] != null ? Number(b.bbox[0]) : 0
      if (ax !== bx) return ax - bx

      return aItem.index - bItem.index
    })
    return arr.map(item => item.block)
  }, [blocks])

  useEffect(() => {
    try { localStorage.setItem('reader.twoColumn', twoColumn ? '1' : '0') } catch {}
  }, [twoColumn])

  // Intersection Observer for Progress
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            setReadBlocks(prev => new Set([...prev, entry.target.id]))
          }
        })
      },
      { root: panelRef.current, threshold: 0.5 }
    )
    
    const elements = document.querySelectorAll('[data-block]')
    elements.forEach(el => observer.observe(el))
    
    return () => observer.disconnect()
  }, [blocks, setReadBlocks])

  // Close picker on Escape or outside click
  useEffect(() => {
    const handleKeyDown = (e) => {
        if (e.key === 'Escape') setPickerPos(null)
    }
    const handleClickOutside = (e) => {
        if (panelRef.current && !panelRef.current.contains(e.target)) setPickerPos(null)
    }
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
        document.removeEventListener('keydown', handleKeyDown)
        document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  // Handle Text Selection
  const handleMouseUp = (blockId) => {
    const selection = window.getSelection()
    const text = selection.toString().trim()
    
    if (text && !selection.isCollapsed) {
        const range = selection.getRangeAt(0).cloneRange()
        const rect = range.getBoundingClientRect()

        // Important: selection offsets are relative to the specific container/node.
        // For simplicity in this reader, we'll store the offsets and the text.
        const selectionData = {
            blockId,
            startOffset: selection.anchorOffset,
            endOffset: selection.focusOffset,
            text
        }
        setSelectionRange(selectionData)
        onSelectionChange(selectionData)
        
        setPickerPos({
            top: rect.top - 50,
            left: rect.left + rect.width / 2
        })
    }
  }

  const inlineMarkdown = (text) => {
    if (!text) return ''
    let str = String(text)

    // Pre-fix: insert space when "Table/Figure/Fig X.Y" is stuck to previous word
    // e.g. "inTable 1.1" -> "in Table 1.1", "seeFigure 2.3" -> "see Figure 2.3"
    str = str.replace(/([a-z])(Table|Figure|Fig)\s+(\d+[\.\-]\d+)/g, '$1 $2 $3')

    let html = str
      .replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/(?<!\w)_(.*?)_(?!\w)/g, '<em>$1</em>')
      .replace(/\^(\d+)/g, '<sup>$1</sup>')
      .replace(/\*(?!\*)([^*]*?)\*(?!\*)/g, '$1')

    // Linkify Table/Figure references
    if (referenceIndex && Object.keys(referenceIndex).length > 0) {
      html = html.replace(
        /(?<![a-zA-Z])(Table|Figures?|Figs?\.?)\s+(\d+[\.\-]\d+)(?!\d)/gi,
        (match, type, num) => {
          const variants = [
            `${type.toLowerCase().replace(/s$/, '').replace(/\.$/, '')} ${num}`,
            `${type.toLowerCase()} ${num}`,
            `table ${num}`,
            `figure ${num}`,
            `fig ${num}`,
            `fig. ${num}`,
          ]
          let target = null
          for (const v of variants) {
            if (referenceIndex[v.toLowerCase()]) {
              target = referenceIndex[v.toLowerCase()]
              break
            }
          }
          if (target) {
            return `<a href="#${target.blockId}" data-ref-target="${target.blockId}" class="ref-link">${match}</a>`
          }
          return match
        }
      )
    }

    return html
  }

  // Delegate clicks on reference links to onRefClick
  const handlePanelClick = (e) => {
    const link = e.target.closest('[data-ref-target]')
    if (link) {
      e.preventDefault()
      e.stopPropagation()
      const target = link.getAttribute('data-ref-target')
      console.log('[RefLink] clicked', target, 'onRefClick:', !!onRefClick)
      if (onRefClick) onRefClick(target)
    }
  }

  const renderHighlights = (blockId, html) => {
    const hls = annotations.highlights.filter(h => h.blockId === blockId)
    if (hls.length === 0) return html

    // Ensure html is a string before processing
    let plainText = String(html || '').replace(/<[^>]*>?/gm, '')
    
    // Create an array of ranges to highlight
    const sorted = [...hls].sort((a, b) => a.startOffset - b.startOffset)
    
    let result = ''
    let lastIndex = 0
    
    sorted.forEach(hl => {
        const start = Math.min(hl.startOffset, hl.endOffset)
        const end = Math.max(hl.startOffset, hl.endOffset)
        
        // Add text before highlight
        result += plainText.substring(lastIndex, start)
        // Add highlighted text
        result += `<mark style="background: ${hl.color}; border-radius: 2px; padding: 0 2px; cursor: pointer" data-hl-id="${hl.id}">`
        result += plainText.substring(start, end)
        result += `</mark>`
        
        lastIndex = end
    })
    
    // Add remaining text
    result += plainText.substring(lastIndex)
    
    // Now apply inline markdown to the whole thing
    return inlineMarkdown(result)
  }

  const renderBlock = (block) => {
    switch (block.type) {
      case 'heading': {
        const Tag = `h${block.level + 1}`
        
        // Ensure block.text is a string
        const blockText = String(block.text || '')
        
        // Convert ALL CAPS to Title Case for display
        const displayText = blockText === blockText.toUpperCase() && blockText.length > 3
          ? blockText.toLowerCase().replace(/\b\w/g, c => c.toUpperCase())
          : blockText

        return (
          <Tag
            key={block.id}
            id={block.id}
            data-block
            className={`reader-h${block.level}`}
          >
            {displayText}
          </Tag>
        )
      }

      case 'paragraph': {
        // Ensure block.text is a string
        const blockText = String(block.text || '')
        // Step 1: apply highlights (returns HTML string with <mark> tags)
        const withHighlights = renderHighlights(block.id, blockText)
        // Step 2: apply inline markdown on top
        const finalHtml = inlineMarkdown(withHighlights)
        return (
          <p
            key={block.id}
            id={block.id}
            data-block
            onMouseUp={() => handleMouseUp(block.id)}
            className="reader-p"
            dangerouslySetInnerHTML={{ __html: finalHtml }}
          />
        )
      }

      case 'list': {
        const isDefinition = block.style === 'definition'
        const isNumbered = block.style === 'numbered'
        const Tag = isNumbered ? 'ol' : 'ul'

        return (
          <Tag 
            key={block.id} 
            id={block.id} 
            data-block 
            style={{
              margin: '10px 0 24px 0',
              paddingLeft: '24px',
              listStyleType: isNumbered ? 'decimal' : 'disc',
            }}
          >
            {(block.items || []).map((item, idx) => {
              if (isDefinition && typeof item === 'object' && item !== null) {
                return (
                  <li key={idx} style={{
                      fontSize: '15px',
                      lineHeight: '1.7',
                      color: 'var(--text-secondary)',
                      marginBottom: '12px',
                    }}>
                    <strong dangerouslySetInnerHTML={{ __html: inlineMarkdown(String(item.term || '')) }} />
                    {item.definition && (
                      <span className="definition-content">
                        : <span dangerouslySetInnerHTML={{ __html: inlineMarkdown(String(item.definition)) }} />
                      </span>
                    )}
                  </li>
                )
              }

              // Handle nested or complex items
              let content = ''
              if (item && typeof item === 'object') {
                if ('text' in item) content = String(item.text)
                else if ('term' in item) content = `**${item.term}**: ${item.definition || ''}`
                else content = JSON.stringify(item)
              } else if (Array.isArray(item)) {
                content = item.map(c => String(c || '')).join(' ')
              } else {
                content = String(item || '')
              }

              if (!content.trim()) return null

              return (
                <li 
                  key={idx} 
                  style={{
                    fontSize: '15px',
                    lineHeight: '1.7',
                    color: 'var(--text-secondary)',
                    marginBottom: '8px',
                  }}
                  dangerouslySetInnerHTML={{ __html: inlineMarkdown(content) }}
                />
              )
            })}
          </Tag>
        )
      }


      case 'table': {
        return <TableComponent block={block} inlineMarkdown={inlineMarkdown} />
      }

      case 'callout': {
        const variants = {
          'Clinical Pearl':  { bg: 'rgba(37, 99, 235, 0.05)', border: '#BFDBFE', label: '#1D4ED8', text: '#1E40AF' },
          'Warning':         { bg: 'rgba(249, 115, 22, 0.05)',  border: '#FED7AA', label: '#C2410C', text: '#9A3412' },
          'Important':       { bg: 'rgba(249, 115, 22, 0.05)',  border: '#FED7AA', label: '#C2410C', text: '#9A3412' },
          'Caution':         { bg: 'rgba(245, 158, 11, 0.05)',  border: '#FDE68A', label: '#B45309', text: '#92400E' },
          'Note':            { bg: 'rgba(16, 185, 129, 0.05)',  border: '#BBF7D0', label: '#15803D', text: '#166534' },
          'Remember':        { bg: 'rgba(139, 92, 246, 0.05)',  border: '#DDD6FE', label: '#7C3AED', text: '#6D28D9' },
          'Key Concept':     { bg: 'rgba(37, 99, 235, 0.05)',  border: '#BFDBFE', label: '#1D4ED8', text: '#1E40AF' },
        }
        const v = variants[String(block.label || '')] || variants['Note']

        return (
          <div
            key={block.id}
            id={block.id}
            data-block
            style={{
              background: v.bg,
              border: `1px solid ${v.border}`,
              borderLeft: `4px solid ${v.label}`,
              borderRadius: '6px',
              padding: '16px 20px',
              margin: '24px 0',
            }}
          >
            <div style={{
              fontSize: '11px',
              fontWeight: 700,
              color: v.label,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              marginBottom: '8px',
            }}>
              {String(block.label || '')}
            </div>
            <div
              style={{ fontSize: '14.5px', color: v.text, lineHeight: '1.6' }}
              dangerouslySetInnerHTML={{ __html: inlineMarkdown(String(block.text || '')) }}
            />
          </div>
        )
      }

      case 'image':
        return (
          <figure key={block.id} id={block.id} data-block style={{ margin: '20px 0', textAlign: 'center' }}>
            <img
              src={block.src}
              alt={block.caption || ''}
              loading="lazy"
              style={{ maxWidth: '100%', borderRadius: '6px', border: '1px solid var(--border)' }}
            />
            {block.caption && (
              <figcaption style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px', fontStyle: 'italic' }}>
                {block.caption}
              </figcaption>
            )}
          </figure>
        )

      case 'mcq': {
        const opts = Array.isArray(block.options) ? block.options : []
        const qnum = block.qnum != null ? String(block.qnum) : ''
        const images = Array.isArray(block.images) ? block.images : []
        return (
          <div
            key={block.id}
            id={block.id}
            data-block
            onMouseUp={() => handleMouseUp(block.id)}
            style={{
              margin: '16px 0',
              padding: '14px 14px 12px',
              border: '1px solid var(--border)',
              borderRadius: 10,
              background: 'var(--bg-surface)',
            }}
          >
            {images.length > 0 && (
              <div style={{
                display: 'flex', flexWrap: 'wrap', gap: 8,
                marginBottom: 10, justifyContent: 'center',
              }}>
                {images.map((im, idx) => (
                  <img
                    key={`${im.src}-${idx}`}
                    src={im.src}
                    alt={`Figure for Q${qnum}`}
                    style={{
                      maxWidth: '100%', maxHeight: 360,
                      border: '1px solid var(--border)',
                      borderRadius: 6, background: '#fff',
                    }}
                    loading="lazy"
                  />
                ))}
              </div>
            )}
            <div style={{ fontSize: 14, fontWeight: 650, color: 'var(--text-primary)', lineHeight: 1.55 }}>
              <span style={{ color: 'var(--accent)', marginRight: 8 }}>{qnum ? `Q${qnum}.` : 'Q.'}</span>
              <span
                dangerouslySetInnerHTML={{
                  __html: inlineMarkdown(String(block.question || '')),
                }}
              />
            </div>
            {opts.length > 0 && (
              <ol
                type="A"
                style={{
                  marginTop: 10,
                  marginBottom: 0,
                  paddingLeft: 22,
                  color: 'var(--text-secondary)',
                  lineHeight: 1.65,
                  fontSize: 13.5,
                }}
              >
                {opts.map((o, idx) => (
                  <li key={`${o.key || idx}-${idx}`} style={{ marginBottom: 6 }}>
                    <span dangerouslySetInnerHTML={{ __html: inlineMarkdown(String(o.text || '')) }} />
                  </li>
                ))}
              </ol>
            )}
            {block.answer && (
              <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-muted)' }}>
                Answer: <strong style={{ color: 'var(--text-primary)' }}>{String(block.answer)}</strong>
              </div>
            )}
            {block.explanation && (
              <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                <span style={{ fontWeight: 650, color: 'var(--text-primary)' }}>Explanation:</span>{' '}
                <span dangerouslySetInnerHTML={{ __html: inlineMarkdown(String(block.explanation)) }} />
              </div>
            )}
          </div>
        )
      }

      default:
        console.warn('Unknown block type:', block.type, block)
        return null
    }
  }

  return (
    <main
        ref={panelRef}
        className="text-panel"
        onClick={handlePanelClick}
        style={{
            height: '100%',
            overflowY: 'auto',
            background: 'var(--bg-base)',
            position: 'relative'
        }}
    >
      <button
        onClick={() => setTwoColumn(v => !v)}
        title={twoColumn ? 'Switch to single column' : 'Switch to two-column (book layout)'}
        style={{
          position: 'absolute',
          top: 16,
          right: 20,
          zIndex: 10,
          background: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: '6px 10px',
          fontSize: 12,
          color: 'var(--text-secondary)',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {twoColumn ? '⬛⬛' : '⬛'} {twoColumn ? '2-col' : '1-col'}
      </button>
        <div className={`reader-container${twoColumn ? ' two-column' : ''}`}>
          {sortedBlocks.length > 0 ? (
            sortedBlocks.map(renderBlock)
          ) : (
              <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
                  {activeChapterId ? (
                    <div>
                      <p>No content found for this chapter.</p>
                      <p style={{ fontSize: '12px', marginTop: '16px' }}>
                        Chapter ID: {activeChapterId}
                      </p>
                    </div>
                  ) : (
                    <p>Select a chapter to begin reading.</p>
                  )}
              </div>
          )}
      </div>

      {/* Floating Highlight Picker */}
      {pickerPos && (
          <div style={{
              position: 'fixed',
              top: pickerPos.top,
              left: pickerPos.left,
              transform: 'translateX(-50%)',
              zIndex: 2000,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '6px',
              display: 'flex',
              gap: '6px',
              boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)'
          }}>
              {[
                  { label: 'Yellow', color: '#FEF3C7' },
                  { label: 'Blue', color: '#DBEAFE' },
                  { label: 'Green', color: '#D1FAE5' },
                  { label: 'Pink', color: '#FCE7F3' }
              ].map(chip => (
                  <button 
                    key={chip.label}
                    onClick={() => {
                        onAddHighlight({
                            ...selectionRange,
                            color: chip.color,
                            colorLabel: chip.label,
                            id: crypto.randomUUID(),
                            createdAt: new Date().toISOString()
                        })
                        setPickerPos(null)
                        window.getSelection().removeAllRanges()
                    }}
                    style={{ 
                        width: '24px', 
                        height: '24px', 
                        borderRadius: '50%', 
                        background: chip.color,
                        border: '1px solid rgba(0,0,0,0.1)',
                        cursor: 'pointer'
                    }} 
                  />
              ))}
              <div style={{ width: '1px', background: 'var(--border)', margin: '0 4px' }} />
              <button 
                onClick={() => {
                    setPickerPos(null)
                    // Note input is handled in AnnotationPanel now
                }}
                style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-secondary)',
                    fontSize: '12px',
                    cursor: 'pointer',
                    padding: '0 8px'
                }}
              >
                  Note (in sidebar)
              </button>
          </div>
      )}
    </main>
  )
}
