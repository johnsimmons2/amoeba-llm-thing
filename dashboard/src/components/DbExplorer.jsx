import { useState, useEffect } from 'react'

export default function DbExplorer() {
  const [db, setDb] = useState('logs')
  const [tables, setTables] = useState({})
  const [sql, setSql] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch(`/api/db/tables?db=${db}`)
      .then((r) => r.json())
      .then((d) => { setTables(d.tables || {}); setError(d.error || '') })
      .catch(() => setError('Failed to load tables'))
  }, [db])

  const runQuery = async () => {
    if (!sql.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await fetch('/api/db/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: sql.trim(), db }),
      })
      const data = await res.json()
      if (data.error) {
        setError(data.error)
      } else {
        setResult(data)
      }
    } catch {
      setError('Query failed')
    }
    setLoading(false)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      runQuery()
    }
  }

  return (
    <div style={container}>
      {/* DB selector + schema */}
      <div style={topBar}>
        <div style={schemaPanel}>
          <div style={dbSelector}>
            {['logs', 'context'].map((d) => (
              <button
                key={d}
                style={db === d ? btnActive : btn}
                onClick={() => setDb(d)}
              >
                {d}.db
              </button>
            ))}
          </div>
          <div style={schemaList}>
            {Object.entries(tables).map(([tbl, cols]) => (
              <div key={tbl} style={{ marginBottom: 8 }}>
                <div style={tableName}>{tbl}</div>
                {cols.map((c) => (
                  <div key={c.name} style={colRow}>
                    <span style={colName}>{c.name}</span>
                    <span style={colType}>{c.type}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* Query input */}
        <div style={queryPanel}>
          <textarea
            style={queryInput}
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKey}
            placeholder="SELECT * FROM logs ORDER BY id DESC LIMIT 20"
            rows={3}
          />
          <div style={queryActions}>
            <button style={runBtn} onClick={runQuery} disabled={loading}>
              {loading ? 'Running…' : 'Run (Ctrl+Enter)'}
            </button>
            <span style={hintText}>Read-only: SELECT, PRAGMA, EXPLAIN, WITH</span>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && <div style={errorBox}>{error}</div>}

      {/* Results table */}
      {result && (
        <div style={resultArea}>
          <div style={resultMeta}>{result.count} row{result.count !== 1 ? 's' : ''}</div>
          <div style={tableWrap}>
            <table style={table}>
              <thead>
                <tr>
                  {result.columns.map((c) => (
                    <th key={c} style={th}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j} style={td}>{formatCell(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function formatCell(v) {
  if (v === null) return 'NULL'
  if (typeof v === 'string' && v.length > 200) return v.slice(0, 200) + '…'
  return String(v)
}

// ── styles ───────────────────────────────────────────────────────────────────

const container = { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }

const topBar = { display: 'flex', gap: 12, padding: '12px 16px', borderBottom: '1px solid #21262d', flexShrink: 0 }

const schemaPanel = { width: 200, flexShrink: 0 }
const dbSelector = { display: 'flex', gap: 4, marginBottom: 8 }

const btn = {
  fontSize: 10, fontWeight: 500, fontFamily: 'inherit',
  color: '#8b949e', background: '#161b22', border: '1px solid #21262d',
  borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
}
const btnActive = {
  ...btn, color: '#e6edf3', background: '#30363d', borderColor: '#58a6ff',
}

const schemaList = { fontSize: 11, overflowY: 'auto', maxHeight: 120 }
const tableName = { color: '#58a6ff', fontWeight: 600, fontSize: 11, marginBottom: 2 }
const colRow = { display: 'flex', gap: 6, paddingLeft: 8 }
const colName = { color: '#c9d1d9' }
const colType = { color: '#484f58', fontSize: 10 }

const queryPanel = { flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }
const queryInput = {
  flex: 1, background: '#161b22', border: '1px solid #30363d', borderRadius: 6,
  color: '#e6edf3', padding: '8px 12px', fontFamily: 'inherit', fontSize: 12,
  outline: 'none', resize: 'none', minHeight: 50,
}
const queryActions = { display: 'flex', alignItems: 'center', gap: 10 }
const runBtn = {
  background: '#238636', border: 'none', borderRadius: 6, color: '#fff',
  padding: '5px 14px', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit',
}
const hintText = { fontSize: 10, color: '#484f58' }

const errorBox = {
  margin: '8px 16px', padding: '6px 12px', background: '#f8514918',
  border: '1px solid #f85149', borderRadius: 6, color: '#f85149', fontSize: 12,
}

const resultArea = { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }
const resultMeta = { padding: '6px 16px', fontSize: 10, color: '#8b949e' }
const tableWrap = { flex: 1, overflowX: 'auto', overflowY: 'auto', padding: '0 16px 16px' }

const table = { width: '100%', borderCollapse: 'collapse', fontSize: 11 }
const th = {
  textAlign: 'left', padding: '4px 8px', borderBottom: '1px solid #30363d',
  color: '#8b949e', fontWeight: 600, position: 'sticky', top: 0,
  background: '#0d1117', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5,
}
const td = {
  padding: '3px 8px', borderBottom: '1px solid #161b22', color: '#c9d1d9',
  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxWidth: 400,
}
