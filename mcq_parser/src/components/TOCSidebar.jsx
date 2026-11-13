import React, { useState } from 'react'

export default function TOCSidebar({ 
    chapters, 
    activeBlockId, 
    onBlockSelect, 
    readBlocks, 
    totalBlocks,
    bookmarks 
}) {
  const [collapsedChapters, setCollapsedChapters] = useState({})
  const [searchQuery, setSearchQuery] = useState('')

  const toggleChapter = (chId) => {
    setCollapsedChapters(prev => ({
        ...prev,
        [chId]: !prev[chId]
    }))
  }

  const progressPercent = totalBlocks > 0 ? (readBlocks.size / totalBlocks) * 100 : 0

  const filteredChapters = chapters?.filter(ch => 
    ch.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ch.sections.some(s => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
  ) || []

  return (
    <aside className="toc-sidebar" style={{
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden'
    }}>
      <div style={{ padding: '16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.05em' }}>
            Book Contents
        </div>
        
        {/* Progress Bar */}
        <div style={{ height: '4px', background: 'var(--border)', borderRadius: '2px', overflow: 'hidden', marginBottom: '16px' }}>
            <div style={{ 
                height: '100%', 
                background: '#10B981', 
                width: `${progressPercent}%`,
                transition: 'width 0.3s ease'
            }} />
        </div>

        <input 
            type="text" 
            placeholder="Search chapters..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
                width: '100%',
                background: 'var(--bg-base)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                padding: '6px 10px',
                fontSize: '12px',
                color: 'var(--text-primary)',
                outline: 'none'
            }}
        />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
        {filteredChapters.map(ch => {
            const isCollapsed = collapsedChapters[ch.id]
            const totalChBlocks = ch.sections.reduce((acc, s) => acc + s.blocks.length, 0)
            const readChBlocks = ch.sections.reduce((acc, s) => acc + s.blocks.filter(b => readBlocks.has(b.id)).length, 0)
            
            let statusColor = '#D1D5DB' // grey
            if (readChBlocks === totalChBlocks && totalChBlocks > 0) statusColor = '#10B981' // green
            else if (readChBlocks > 0) statusColor = '#F59E0B' // amber

            return (
                <div key={ch.id} style={{ marginBottom: '4px' }}>
                    <div 
                        onClick={() => {
                            toggleChapter(ch.id)
                            // When clicking chapter header, also select first section if not already
                            if (ch.sections.length > 0 && ch.sections[0].blocks.length > 0) {
                                onBlockSelect(ch.sections[0].blocks[0].id)
                            }
                        }}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '6px 16px',
                            cursor: 'pointer',
                            transition: 'background 0.2s'
                        }}
                        className="toc-chapter-header"
                    >
                        <div style={{ width: '8px', height: '8px', background: statusColor, borderRadius: '50%' }} />
                        <span style={{ 
                            fontSize: '13px', 
                            fontWeight: 600, 
                            color: 'var(--text-primary)',
                            flex: 1,
                            letterSpacing: '-0.01em'
                        }}>{ch.title}</span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{isCollapsed ? '▸' : '▾'}</span>
                    </div>

                    {!isCollapsed && (
                        <div style={{ paddingLeft: '12px' }}>
                            {ch.sections.map(sec => {
                                const isActive = activeBlockId?.startsWith(sec.id)
                                const blockId = sec.blocks[0]?.id
                                return (
                                    <div 
                                        key={sec.id}
                                        onClick={() => {
                                            if (blockId) {
                                                onBlockSelect(blockId)
                                            } else {
                                                console.warn(`Section ${sec.id} has no blocks`)
                                            }
                                        }}
                                        style={{
                                            padding: '6px 20px',
                                            cursor: blockId ? 'pointer' : 'not-allowed',
                                            fontSize: '12px',
                                            color: isActive ? 'var(--accent)' : (blockId ? 'var(--text-secondary)' : 'var(--text-muted)'),
                                            background: isActive ? 'var(--bg-elevated)' : 'transparent',
                                            fontWeight: isActive ? 550 : 400,
                                            borderLeft: isActive ? '3px solid var(--accent)' : '3px solid transparent',
                                            transition: 'all 0.15s'
                                        }}
                                        className="toc-section-item"
                                    >
                                        {sec.title}
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>
            )
        })}
      </div>

      {bookmarks?.length > 0 && (
          <div style={{ padding: '16px', borderTop: '1px solid var(--border)', background: 'var(--bg-base)' }}>
            <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
                Bookmarks
            </div>
            {bookmarks.map(bm => (
                <div 
                    key={bm.blockId}
                    onClick={() => onBlockSelect(bm.blockId)}
                    style={{ 
                        fontSize: '12px', 
                        color: 'var(--text-secondary)', 
                        padding: '4px 0', 
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                    }}
                    title={`${bm.chapterTitle} > ${bm.sectionTitle}`}
                >
                    🔖 {bm.sectionTitle}
                </div>
            ))}
          </div>
      )}

      <style>{`
        .toc-chapter-header:hover { background: var(--bg-hover); }
        .toc-section-item:hover { background: var(--bg-hover); }
      `}</style>
    </aside>
  )
}
