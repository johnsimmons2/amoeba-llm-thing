import { useState, useEffect, useRef } from 'react'

const API = '/api/notes'

export default function NotesBrowser() {
  const [notes, setNotes] = useState([])
  const [query, setQuery] = useState('')
  const [topicFilter, setTopicFilter] = useState('')
  const [expanded, setExpanded] = useState(new Set())
  const timer = useRef(null)

  const fetchNotes = () => {
    const params = new URLSearchParams()
    if (query) params.set('q', query)
    if (topicFilter) params.set('topic', topicFilter)
    params.set('limit', '100')
    fetch(`${API}?${params}`)
      .then((r) => r.json())
      .then(setNotes)
      .catch(() => {})
  }

  useEffect(() => {
    fetchNotes()
    timer.current = setInterval(fetchNotes, 8000)
    return () => clearInterval(timer.current)
  }, [query, topicFilter])

  const toggle = (id) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const topics = [...new Set(notes.map((n) => n.topic))].sort()

  return (
    <div style={container}>
      <div style={toolbar}>
        <input
          style={searchInput}
          placeholder="Search notes…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          style={selectStyle}
          value={topicFilter}
          onChange={(e) => setTopicFilter(e.target.value)}
        >
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <span style={countLabel}>{notes.length} notes</span>
      </div>

      <div style={listArea}>
        {notes.length === 0 && (
          <div style={emptyMsg}>
            {query ? 'No matching notes.' : 'No notes yet — agents will save discoveries here.'}
          </div>
        )}
        {notes.map((n) => {
          const open = expanded.has(n.id)
          const tags = (() => {
            try { return JSON.parse(n.tags) } catch { return [] }
          })()
          return (
            <div key={n.id} style={noteCard} onClick={() => toggle(n.id)}>
              <div style={noteHeader}>
                <span style={topicBadge}>{n.topic}</span>
                <span style={agentLabel}>{n.agent_id}</span>
                {tags.length > 0 && tags.map((t) => (
                  <span key={t} style={tagChip}>{t}</span>
                ))}
                <span style={timeLabel}>{n.created_at?.slice(0, 16).replace('T', ' ')}</span>
                <span style={idLabel}>#{n.id}</span>
              </div>
              <div style={noteBody}>
                {open ? n.content : n.content.slice(0, 200) + (n.content.length > 200 ? '…' : '')}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const container = { display: 'flex', flexDirection: 'column', height: '100%' }

const toolbar = {
  display: 'flex', gap: 8, padding: '8px 12px',
  borderBottom: '1px solid #21262d', alignItems: 'center', flexShrink: 0,
}

const searchInput = {
  flex: 1, background: '#0d1117', border: '1px solid #30363d',
  borderRadius: 4, padding: '5px 10px', color: '#c9d1d9',
  fontSize: 12, outline: 'none', maxWidth: 300,
}

const selectStyle = {
  background: '#0d1117', border: '1px solid #30363d',
  borderRadius: 4, padding: '5px 8px', color: '#8b949e', fontSize: 11,
}

const countLabel = { fontSize: 10, color: '#484f58', marginLeft: 'auto' }

const listArea = { flex: 1, overflowY: 'auto', padding: '4px 0' }

const emptyMsg = { padding: '40px 20px', color: '#484f58', textAlign: 'center', fontSize: 12 }

const noteCard = {
  margin: '4px 12px', padding: '8px 12px', background: '#161b22',
  borderRadius: 6, borderLeft: '3px solid #3fb950', cursor: 'pointer',
}

const noteHeader = {
  display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4,
}

const topicBadge = {
  fontSize: 10, fontWeight: 700, color: '#3fb950',
  background: '#3fb95018', borderRadius: 3, padding: '1px 6px',
}

const agentLabel = { fontSize: 10, color: '#8b949e' }

const tagChip = {
  fontSize: 9, color: '#d2a8ff', background: '#d2a8ff14',
  borderRadius: 3, padding: '1px 5px',
}

const timeLabel = { fontSize: 10, color: '#484f58', marginLeft: 'auto' }
const idLabel = { fontSize: 9, color: '#30363d' }

const noteBody = {
  fontSize: 11.5, color: '#c9d1d9', whiteSpace: 'pre-wrap',
  wordBreak: 'break-word', lineHeight: 1.5,
}
