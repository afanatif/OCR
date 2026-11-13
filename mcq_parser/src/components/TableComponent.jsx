import React, { useMemo, useState } from 'react'

// Split a cell's text into bullet list items. Tries three strategies in order:
//   1. Newline separation (cell already has explicit line breaks)
//   2. Inline bullet markers • or ● (TableFormer sometimes emits them inline)
//   3. Capitalized-sentence heuristic: split run-on text like
//      "Can be converted to glucose... Synthesized in mammary gland..."
//      where each bullet starts with a Capitalized word after a lowercase
//      word — but only if there are ≥2 such transitions, indicating a real
//      list rather than normal prose.
function splitIntoBullets(text) {
  if (!text) return [text].filter(Boolean)
  const str = String(text).trim()
  // Strategy 1: newlines
  const byNewline = str.split(/\n+/).map(s => s.trim()).filter(Boolean)
  if (byNewline.length > 1) {
    return byNewline.map(s => s.replace(/^[•●\-\*]\s*/, ''))
  }
  // Strategy 2: inline bullet markers
  if ((str.match(/[•●]/g) || []).length >= 2) {
    return str.split(/\s*[•●]\s*/).map(s => s.trim()).filter(Boolean)
  }
  // Strategy 3: capitalized-sentence splitting for run-on merged bullets.
  // Look for places where a complete-looking clause is followed by a known
  // sentence-starter word (e.g. "...FAD Intermediate product...").
  // SENTENCE_STARTERS is restrictive so even 1 split is trustworthy.
  const SENTENCE_STARTERS = new Set([
    'Can','Synthesized','A','The','An','Intermediate','Constituent',
    'Precursor','Involved','Used','Found','Present','Required',
    'Essential','Important','Helps','Acts','Serves','Provides',
    'Produced','Maintains','Regulates','Responsible','Contains',
  ])
  const words = str.split(/\s+/)
  const splitPoints = [0]
  for (let w = 1; w < words.length; w++) {
    const prev = words[w - 1]
    const cur = words[w]
    // Prev ends in any letter — allows acronyms like "FAD", "RNA", "ATP"
    // to be followed by a new bullet starting with a sentence-starter word.
    if (!/[a-zA-Z]$/.test(prev)) continue
    if (!SENTENCE_STARTERS.has(cur)) continue
    // Require at least 3 words since last split so we don't split mid-phrase
    const lastSplit = splitPoints[splitPoints.length - 1]
    if (w - lastSplit < 3) continue
    splitPoints.push(w)
  }
  if (splitPoints.length >= 2) {
    // ≥1 internal split → ≥2 segments
    splitPoints.push(words.length)
    const segments = []
    for (let p = 0; p < splitPoints.length - 1; p++) {
      const seg = words.slice(splitPoints[p], splitPoints[p + 1]).join(' ').trim()
      if (seg.length >= 15) segments.push(seg)
    }
    if (segments.length >= 2) return segments
  }
  return [str]
}

export default function TableComponent({ block, inlineMarkdown }) {
  const rawHeaders = block.headers || []
  const caption = block.caption || ''
  const imageSrc = block.image_src || ''

  // Default to image view when one is available (pixel-perfect), but let
  // users toggle to the parsed text table for copy/paste and accessibility.
  const [showAsImage, setShowAsImage] = useState(!!imageSrc)

  // Safely filter rows - convert cells to strings and check if they have content
  const rows = (block.rows || []).filter(row => {
    if (!Array.isArray(row)) return false
    return row.some(cell => {
      const cellStr = String(cell || '').trim()
      return cellStr.length > 0
    })
  })

  // Legacy fallback: if headers still contain a caption pattern
  // (for older data without explicit caption field)
  const firstHeader = String(rawHeaders[0] || '')
  const looksLikeCaption = !caption && (
    firstHeader.match(/^Table\s+\d+[\.:]/i) ||
    (firstHeader.length > 50 && rawHeaders.slice(1).every(h => !h || h === '—'))
  )

  const headers = looksLikeCaption && rows.length > 0 ? rows[0] : rawHeaders
  const dataRows = looksLikeCaption && rows.length > 0 ? rows.slice(1) : rows
  const displayCaption = caption || (looksLikeCaption ? firstHeader : '')

  const hasTextData = headers.length > 0 || dataRows.length > 0
  if (!hasTextData && !imageSrc) {
    return null
  }

  const displayHeaders = headers.length > 0 ? headers : (dataRows[0] || [])
  const displayRows = headers.length > 0 ? dataRows : dataRows.slice(1)

  // Auto-rowspan: for each LEADING column (left-most), collapse consecutive
  // identical values into a single cell spanning multiple rows — matches the
  // book's visual grouping (e.g. "Pentoses" spanning 4 sub-rows instead of
  // repeating in every row). A column stops being "leading" for a given row
  // once we encounter a column with distinct per-row content.
  const rowspanMap = useMemo(() => {
    // map[rowIdx][colIdx] = rowspan integer (1 = normal cell, 0 = hidden because
    // absorbed by a prior rowspan, >1 = render with rowspan=N and skip next N-1)
    const map = displayRows.map(() => [])
    const n = displayRows.length
    for (let c = 0; c < (displayHeaders.length || 0); c++) {
      let i = 0
      while (i < n) {
        const val = String((displayRows[i] || [])[c] ?? '').trim()
        if (!val) { map[i][c] = 1; i++; continue }
        // Count run of identical values starting at i
        let j = i + 1
        while (j < n && String((displayRows[j] || [])[c] ?? '').trim() === val) j++
        const run = j - i
        // Only collapse columns where the run is real (>=2). Also require
        // that further columns differ somewhere inside the run — otherwise
        // the whole rows are duplicates and we shouldn't collapse here.
        let shouldCollapse = run >= 2
        if (shouldCollapse) {
          // Check that at least one later column differs within this run
          let hasVariation = false
          for (let k = c + 1; k < displayHeaders.length && !hasVariation; k++) {
            const first = String((displayRows[i] || [])[k] ?? '').trim()
            for (let r = i + 1; r < j; r++) {
              if (String((displayRows[r] || [])[k] ?? '').trim() !== first) {
                hasVariation = true
                break
              }
            }
          }
          if (!hasVariation) shouldCollapse = false
        }
        if (shouldCollapse) {
          map[i][c] = run
          for (let k = i + 1; k < j; k++) map[k][c] = 0
        } else {
          for (let k = i; k < j; k++) map[k][c] = 1
        }
        i = j
      }
    }
    return map
  }, [displayRows, displayHeaders])

  // Calculate optimal column widths based on content
  const columnCount = displayHeaders.length
  const baseWidth = 100 / columnCount
  
  // Analyze content to adjust column widths
  const columnWidths = useMemo(() => {
    const widths = Array(columnCount).fill(baseWidth)
    
    // Check header lengths
    displayHeaders.forEach((h, i) => {
      const headerLength = (String(h || '')).length
      if (headerLength > 20) widths[i] = Math.max(widths[i], 18)
      else if (headerLength > 10) widths[i] = Math.max(widths[i], 14)
    })
    
    // Normalize so they sum to 100
    const total = widths.reduce((a, b) => a + b, 0)
    return widths.map(w => (w / total) * 100)
  }, [displayHeaders, columnCount])

  // Image-mode rendering: pixel-perfect crop from the PDF
  if (showAsImage && imageSrc) {
    return (
      <figure className="table-figure" id={block.id} data-block>
        <img
          src={imageSrc}
          alt={displayCaption || caption || 'Table'}
          loading="lazy"
          className="table-image"
        />
        {(displayCaption || caption) && (
          <figcaption className="table-caption">
            {displayCaption || caption}
          </figcaption>
        )}
        {hasTextData && (
          <button
            type="button"
            className="table-mode-toggle"
            onClick={() => setShowAsImage(false)}
            aria-label="Show table as selectable text"
          >
            Show as text
          </button>
        )}
      </figure>
    )
  }

  // Text-mode rendering: parsed HTML table
  return (
    <div
      key={block.id}
      id={block.id}
      data-block
      className="table-wrapper"
      style={{
        margin: '24px 0',
        borderRadius: '8px',
        border: '1px solid var(--border)',
        overflow: 'hidden',
      }}
    >
      {displayCaption && (
        <div style={{
          padding: '12px 16px',
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border)',
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--text-primary)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '12px',
        }}>
          <span>{displayCaption}</span>
          {imageSrc && (
            <button
              type="button"
              className="table-mode-toggle"
              onClick={() => setShowAsImage(true)}
              aria-label="Show original table image from the book"
            >
              Show as image
            </button>
          )}
        </div>
      )}
      {!displayCaption && imageSrc && (
        <div style={{
          padding: '8px 12px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'flex-end',
        }}>
          <button
            type="button"
            className="table-mode-toggle"
            onClick={() => setShowAsImage(true)}
            aria-label="Show original table image from the book"
          >
            Show as image
          </button>
        </div>
      )}
      <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <table className="book-table">
        <thead>
          <tr>
            {displayHeaders.map((h, i) => (
              <th
                key={i}
                style={{
                  width: `${columnWidths[i]}%`,
                  minWidth: '80px',
                  background: 'var(--bg-surface)',
                  padding: '12px 14px',
                  textAlign: 'left',
                  fontWeight: 700,
                  color: 'var(--text-primary)',
                  borderBottom: '2px solid var(--border)',
                  fontSize: '13px',
                  lineHeight: '1.4',
                  wordWrap: 'break-word',
                  overflowWrap: 'break-word',
                  hyphens: 'auto',
                  verticalAlign: 'middle',
                }}
                className="table-header-cell"
              >
                {String(h || '')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, i) => {
            const paddedRow = [...(row || [])].concat(
              Array(Math.max(0, displayHeaders.length - (row || []).length)).fill('')
            )
            return (
              <tr 
                key={i} 
                style={{ 
                  background: i % 2 === 0 ? 'transparent' : 'var(--bg-surface)',
                  borderTop: 'none'
                }}
                className={i % 2 === 0 ? 'table-row-even' : 'table-row-odd'}
              >
                {paddedRow.slice(0, displayHeaders.length).map((cell, j) => {
                  const span = (rowspanMap[i] && rowspanMap[i][j]) ?? 1
                  if (span === 0) return null // absorbed by a prior rowspan
                  const cellText = String(cell || '')
                  // Detect bullet-list cells: multiple lines, or multiple
                  // bullet markers (•) on one run-on line. Split and render
                  // as a proper <ul> so each point gets its own line.
                  const bulletItems = splitIntoBullets(cellText)
                  return (
                    <td
                      key={j}
                      rowSpan={span > 1 ? span : undefined}
                      style={{
                        width: `${columnWidths[j]}%`,
                        minWidth: '80px',
                        padding: '12px 14px',
                        borderBottom:
                          i < displayRows.length - 1
                            ? '1px solid var(--border)'
                            : 'none',
                        color: 'var(--text-secondary)',
                        verticalAlign: 'top',
                        lineHeight: '1.6',
                        fontSize: '13.5px',
                        wordWrap: 'break-word',
                        overflowWrap: 'break-word',
                        hyphens: 'auto',
                        textAlign: 'left',
                        background: span > 1 ? 'var(--bg-surface)' : undefined,
                      }}
                      className="table-data-cell"
                    >
                      {bulletItems.length > 1 ? (
                        <ul style={{
                          margin: 0,
                          paddingLeft: '18px',
                          listStyleType: 'disc',
                        }}>
                          {bulletItems.map((it, k) => (
                            <li
                              key={k}
                              style={{ marginBottom: '6px' }}
                              dangerouslySetInnerHTML={{ __html: inlineMarkdown(it) }}
                            />
                          ))}
                        </ul>
                      ) : (
                        <span dangerouslySetInnerHTML={{
                          __html: inlineMarkdown(cellText).replace(/\n/g, '<br/>')
                        }} />
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
    </div>
  )
}
