import React, { useState, useEffect, useRef } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
// Vite-bundled worker (avoids external CDN issues)
import pdfWorkerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerSrc

// URL-encode path segments (preserve slashes) so spaces etc. work
function encodePdfUrl(url) {
  if (!url) return url
  return url.split('/').map(seg => encodeURIComponent(seg)).join('/')
}

export default function PDFViewer({ pdfUrl, initialPage = 1, show }) {
  const [pdf, setPdf] = useState(null)
  const [currentPage, setCurrentPage] = useState(initialPage)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const canvasRef = useRef(null)

  useEffect(() => {
    if (!pdfUrl) return

    setLoading(true)
    setError(null)
    const safeUrl = encodePdfUrl(pdfUrl)
    const loadingTask = pdfjsLib.getDocument(safeUrl)
    loadingTask.promise.then(
      (loadedPdf) => {
        setPdf(loadedPdf)
        setLoading(false)
      },
      (err) => {
        console.error('Error loading PDF:', err)
        setError(err?.message || 'Failed to load PDF')
        setLoading(false)
      }
    )
  }, [pdfUrl])

  // Follow external page navigation
  useEffect(() => {
    if (initialPage && initialPage !== currentPage) {
      setCurrentPage(initialPage)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPage])

  useEffect(() => {
    if (!pdf || !canvasRef.current || !show) return
    const safePage = Math.max(1, Math.min(currentPage, pdf.numPages))
    pdf.getPage(safePage).then((page) => {
      const viewport = page.getViewport({ scale: 1.5 })
      const canvas = canvasRef.current
      if (!canvas) return
      const context = canvas.getContext('2d')
      canvas.height = viewport.height
      canvas.width = viewport.width
      page.render({ canvasContext: context, viewport })
    }).catch(err => console.error('PDF render error:', err))
  }, [pdf, currentPage, show])

  if (!show) return null

  return (
    <div className="pdf-viewer" style={{
        height: '100%',
        overflow: 'hidden',
        background: 'var(--bg-base)',
        display: 'flex',
        flexDirection: 'column',
        borderLeft: '1px solid var(--border)'
    }}>
      <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: '8px' }}>
        <button 
            disabled={currentPage <= 1} 
            onClick={() => setCurrentPage(p => p - 1)}
            style={{ padding: '4px 8px', fontSize: '12px' }}
        >Prev</button>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Page {currentPage} of {pdf?.numPages || '?'}</span>
        <button 
            disabled={currentPage >= (pdf?.numPages || 0)} 
            onClick={() => setCurrentPage(p => p + 1)}
            style={{ padding: '4px 8px', fontSize: '12px' }}
        >Next</button>
      </div>
      <div style={{ flex: 1, overflow: 'auto', padding: '20px', display: 'flex', justifyContent: 'center' }}>
        {loading ? (
            <div style={{ color: 'var(--text-muted)' }}>Loading PDF...</div>
        ) : error ? (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px' }}>
              <div style={{ marginBottom: '8px' }}>⚠ Could not load PDF</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>{error}</div>
              <div style={{ fontSize: '11px', opacity: 0.5, marginTop: '12px', wordBreak: 'break-all' }}>{pdfUrl}</div>
            </div>
        ) : (
            <canvas ref={canvasRef} style={{ maxWidth: '100%', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }} />
        )}
      </div>
    </div>
  )
}
