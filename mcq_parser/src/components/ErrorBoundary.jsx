import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, info: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('React Error Boundary caught:', error, info)
    this.setState({ error, info })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-base)',
          color: 'var(--text-primary)',
          flexDirection: 'column',
          padding: '20px',
          textAlign: 'center'
        }}>
          <h1 style={{ fontSize: '20px', marginBottom: '12px' }}>⚠️ Error</h1>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Something went wrong while rendering the page
          </p>
          <details style={{
            background: 'var(--bg-surface)',
            padding: '12px',
            borderRadius: '6px',
            maxWidth: '600px',
            textAlign: 'left',
            fontSize: '12px',
            color: 'var(--text-muted)',
            margin: '16px 0',
            border: '1px solid var(--border)'
          }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: '8px' }}>
              Error Details
            </summary>
            <pre style={{ 
              whiteSpace: 'pre-wrap', 
              wordBreak: 'break-word',
              color: '#EF4444'
            }}>
              {this.state.error?.toString()}
            </pre>
            <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {this.state.info?.componentStack}
            </pre>
          </details>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              background: 'var(--accent)',
              color: 'white',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 500
            }}
          >
            Reload Page
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
