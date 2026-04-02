import { useState, useEffect, useRef } from 'react'

const COLLAPSE_THRESHOLD = 600
const AGENT_COLORS = [
  '#58a6ff', '#3fb950', '#f0883e', '#d2a8ff', '#79c0ff',
  '#f85149', '#d29922', '#db61a2', '#7ee787', '#a5d6ff',
]

const colorMap = {}
function agentColor(agentId) {
  if (!colorMap[agentId]) {
    const idx = Object.keys(colorMap).length % AGENT_COLORS.length
    colorMap[agentId] = AGENT_COLORS[idx]
  }
  return colorMap[agentId]
}

const MODEL_TYPES = new Set(['thought', 'thought_delta', 'thought_end', 'tool_call', 'tool_result', 'model_swap'])

function isImageData(s) {
  if (typeof s !== 'string') return false
  return s.startsWith('data:image/') ||
    /^https?:\/\/.+\.(png|jpe?g|gif|webp|svg)(\?|$)/i.test(s)
}

function isAudioData(s) {
  if (typeof s !== 'string') return false
  return s.startsWith('data:audio/') ||
    /^https?:\/\/.+\.(mp3|wav|ogg|m4a|flac)(\?|$)/i.test(s)
}

function CollapsibleText({ text }) {
  const [expanded, setExpanded] = useState(false)
  if (text.length <= COLLAPSE_THRESHOLD) {
    return <span style={textContent}>{text}</span>
  }
  return (
    <div>
      <span style={textContent}>
        {expanded ? text : text.slice(0, COLLAPSE_THRESHOLD) + '\u2026'}
      </span>
      <button onClick={() => setExpanded(!expanded)} style={expandBtn}>
        {expanded ? '\u25B2 collapse' : `\u25BC expand (${text.length} chars)`}
      </button>
    </div>
  )
}

function RichContent({ content }) {
  const text = typeof content === 'object'
    ? JSON.stringify(content, null, 2)
    : String(content ?? '')

  if (isImageData(text)) {
    return <img src={text} alt="model output" style={mediaImg} />
  }
  if (isAudioData(text)) {
    return <audio controls src={text} style={mediaAudio} />
  }
  return <CollapsibleText text={text} />
}

function formatTime(ts) {
  try { return new Date(ts).toLocaleTimeString() } catch { return '' }
}

function ToolCallContent({ content }) {
  if (typeof content !== 'object') return <RichContent content={content} />
  const name = content.tool || '?'
  const args = content.args
    ? JSON.stringify(content.args, null, 2)
    : ''
  return (
    <span style={textContent}>
      <span style={{ color: '#f0883e', fontWeight: 600 }}>{name}</span>
      {args && <span style={{ color: '#8b949e' }}>({args})</span>}
    </span>
  )
}

function ToolResultContent({ content }) {
  if (typeof content !== 'object') return <RichContent content={content} />
  const result = content.result ?? content
  const text = typeof result === 'string' ? result : JSON.stringify(result, null, 2)
  return <CollapsibleText text={text} />
}

export default function ModelOutput({ logs }) {
  const topRef = useRef(null)
  const containerRef = useRef(null)
  const [streamBuf, setStreamBuf] = useState({})

  // Accumulate thought_delta into a per-agent streaming buffer
  useEffect(() => {
    if (logs.length === 0) return
    const last = logs[logs.length - 1]
    if (last.type === 'thought_delta') {
      setStreamBuf((prev) => ({
        ...prev,
        [last.agent_id]: (prev[last.agent_id] || '') + (last.content || ''),
      }))
    } else if (last.type === 'thought_end' || last.type === 'thought') {
      setStreamBuf((prev) => {
        const next = { ...prev }
        delete next[last.agent_id]
        return next
      })
    }
  }, [logs.length])

  const visible = logs.filter((l) =>
    l.type === 'thought' || l.type === 'tool_call' || l.type === 'tool_result' || l.type === 'model_swap'
  )

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const nearTop = el.scrollTop < 120
    if (nearTop) topRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [visible.length, streamBuf])

  const streamEntries = Object.entries(streamBuf).filter(([, text]) => text)

  const reversed = visible.slice().reverse()

  return (
    <div ref={containerRef} style={container}>
      <div ref={topRef} />
      {reversed.length === 0 && streamEntries.length === 0 && (
        <div style={emptyMsg}>Waiting for model output…</div>
      )}

      {streamEntries.map(([agentId, text]) => {
        const color = agentColor(agentId)
        return (
          <div key={`stream-${agentId}`} style={{ ...card, ...streamCard, borderLeftColor: color }}>
            <div style={headerRow}>
              <span style={{ ...agentTag, color, background: `${color}18` }}>
                {agentId}
              </span>
              <span style={streamLabel}>● streaming</span>
            </div>
            <div style={body}>
              <span style={textContent}>{text}</span>
              <span style={streamCursor}>▍</span>
            </div>
          </div>
        )
      })}

      {reversed.map((log, i) => {
        const color = agentColor(log.agent_id)
        return (
          <div key={i} style={{ ...card, borderLeftColor: color }}>
            <div style={headerRow}>
              <span style={{ ...agentTag, color, background: `${color}18` }}>
                {log.agent_id}
              </span>
              <span style={typeLabel(log.type)}>{log.type}</span>
              <span style={timeLabel}>{formatTime(log.timestamp)}</span>
            </div>
            <div style={body}>
              {log.type === 'tool_call'
                ? <ToolCallContent content={log.content} />
                : log.type === 'tool_result'
                  ? <ToolResultContent content={log.content} />
                  : <RichContent content={log.content} />}
            </div>
          </div>
        )
      })}

    </div>
  )
}

// ── styles ───────────────────────────────────────────────────────────────────

const container = { flex: 1, overflowY: 'auto', padding: '8px 0' }
const emptyMsg = { padding: '40px 20px', color: '#484f58', textAlign: 'center' }

const card = {
  borderLeft: '3px solid',
  margin: '6px 12px',
  padding: '6px 12px',
  background: '#161b22',
  borderRadius: '0 6px 6px 0',
}

const headerRow = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginBottom: 4,
}

const agentTag = {
  fontSize: 10,
  fontWeight: 700,
  borderRadius: 3,
  padding: '1px 6px',
  letterSpacing: 0.3,
}

const TYPE_COLORS = {
  thought: '#58a6ff',
  tool_call: '#f0883e',
  tool_result: '#3fb950',
  model_swap: '#d2a8ff',
}

const typeLabel = (type) => ({
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  color: TYPE_COLORS[type] || '#8b949e',
})

const timeLabel = { fontSize: 10, color: '#484f58', marginLeft: 'auto' }
const body = { fontSize: 12, lineHeight: 1.5 }
const textContent = { color: '#c9d1d9', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }
const mediaImg = { maxWidth: '100%', maxHeight: 400, borderRadius: 6, marginTop: 4 }
const mediaAudio = { width: '100%', marginTop: 4 }
const expandBtn = {
  display: 'inline-block',
  marginTop: 4,
  fontSize: 10,
  color: '#58a6ff',
  background: 'transparent',
  border: '1px solid #30363d',
  borderRadius: 3,
  padding: '2px 8px',
  cursor: 'pointer',
  fontFamily: 'inherit',
}

const streamCard = {
  borderColor: '#d29922',
  background: '#d299220a',
}

const streamLabel = {
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0.5,
  color: '#d29922',
}

const streamCursor = {
  color: '#d29922',
  animation: 'blink 1s steps(2) infinite',
  fontSize: 14,
  lineHeight: 1,
  verticalAlign: 'text-bottom',
}
