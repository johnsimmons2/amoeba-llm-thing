import { useState, useEffect } from 'react'

const POLL_MS = 3000
const STATUS_ORDER = ['assigned', 'open', 'done', 'failed']

const statusColor = {
  open: '#8b949e',
  assigned: '#d29922',
  done: '#3fb950',
  failed: '#f85149',
}

const priorityBadge = {
  critical: { bg: '#f8514922', fg: '#f85149' },
  high:     { bg: '#d2992222', fg: '#d29922' },
  normal:   { bg: '#30363d',   fg: '#8b949e' },
  low:      { bg: '#21262d',   fg: '#6e7681' },
}

export default function TaskBoard() {
  const [tasks, setTasks] = useState([])
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    const load = () =>
      fetch('/api/tasks')
        .then((r) => r.json())
        .then(setTasks)
        .catch(() => {})
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [])

  const filtered =
    filter === 'all' ? tasks : tasks.filter((t) => t.status === filter)

  const sorted = [...filtered].sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
      a.created_at.localeCompare(b.created_at)
  )

  const counts = {}
  for (const t of tasks) counts[t.status] = (counts[t.status] || 0) + 1

  return (
    <div style={container}>
      {/* Filter bar */}
      <div style={filterBar}>
        {['all', 'open', 'assigned', 'done', 'failed'].map((f) => (
          <button
            key={f}
            style={filter === f ? btnActive : btn}
            onClick={() => setFilter(f)}
          >
            {f}
            {f !== 'all' && counts[f] ? ` (${counts[f]})` : ''}
            {f === 'all' ? ` (${tasks.length})` : ''}
          </button>
        ))}
      </div>

      {/* Task list */}
      <div style={taskList}>
        {sorted.length === 0 && (
          <div style={empty}>No tasks{filter !== 'all' ? ` with status "${filter}"` : ''}</div>
        )}
        {sorted.map((t) => {
          const pb = priorityBadge[t.priority] || priorityBadge.normal
          return (
            <div key={t.id} style={card}>
              <div style={cardHeader}>
                <span
                  style={{
                    ...statusDot,
                    background: statusColor[t.status] || '#8b949e',
                  }}
                />
                <span style={taskTitle}>{t.title}</span>
                <span
                  style={{
                    ...badge,
                    background: pb.bg,
                    color: pb.fg,
                  }}
                >
                  {t.priority}
                </span>
                <span style={statusLabel}>{t.status}</span>
              </div>
              {t.description && <div style={desc}>{t.description}</div>}
              <div style={meta}>
                {t.assigned_to && (
                  <span style={metaChip}>
                    ▸ {t.assigned_to}
                  </span>
                )}
                {t.created_by && (
                  <span style={metaChip}>by {t.created_by}</span>
                )}
                <span style={metaTime}>{fmtTime(t.created_at)}</span>
                {t.result && (
                  <span style={resultText}>{t.result}</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function fmtTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

// Styles
const container = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  overflow: 'hidden',
}

const filterBar = {
  display: 'flex',
  gap: 4,
  padding: '10px 14px',
  borderBottom: '1px solid #21262d',
  flexShrink: 0,
}

const btn = {
  fontSize: 11,
  fontWeight: 500,
  fontFamily: 'inherit',
  color: '#8b949e',
  background: 'transparent',
  border: '1px solid #30363d',
  borderRadius: 4,
  padding: '3px 10px',
  cursor: 'pointer',
  textTransform: 'capitalize',
}

const btnActive = {
  ...btn,
  color: '#e6edf3',
  background: '#30363d',
  fontWeight: 600,
}

const taskList = {
  flex: 1,
  overflowY: 'auto',
  padding: 14,
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
}

const empty = {
  color: '#484f58',
  fontSize: 12,
  textAlign: 'center',
  marginTop: 40,
}

const card = {
  background: '#161b22',
  border: '1px solid #21262d',
  borderRadius: 6,
  padding: '10px 14px',
}

const cardHeader = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const statusDot = {
  width: 8,
  height: 8,
  borderRadius: '50%',
  flexShrink: 0,
}

const taskTitle = {
  fontSize: 13,
  fontWeight: 600,
  color: '#e6edf3',
  flex: 1,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const badge = {
  fontSize: 10,
  fontWeight: 600,
  padding: '2px 6px',
  borderRadius: 3,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  flexShrink: 0,
}

const statusLabel = {
  fontSize: 10,
  color: '#8b949e',
  textTransform: 'uppercase',
  flexShrink: 0,
}

const desc = {
  fontSize: 12,
  color: '#8b949e',
  marginTop: 6,
  lineHeight: 1.4,
}

const meta = {
  display: 'flex',
  gap: 8,
  marginTop: 6,
  alignItems: 'center',
  flexWrap: 'wrap',
}

const metaChip = {
  fontSize: 10,
  color: '#58a6ff',
  background: '#0d1117',
  border: '1px solid #21262d',
  borderRadius: 3,
  padding: '1px 6px',
}

const metaTime = {
  fontSize: 10,
  color: '#484f58',
  marginLeft: 'auto',
}

const resultText = {
  fontSize: 11,
  color: '#8b949e',
  fontStyle: 'italic',
  maxWidth: 300,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}
