import { useEffect, useRef, useState } from 'react'

const TYPE_COLOR = {
  thought:     '#58a6ff',
  tool_call:   '#f0883e',
  tool_result: '#3fb950',
  spawn:       '#bc8cff',
  kill:        '#f85149',
  error:       '#f85149',
  human:       '#e6edf3',
  message:     '#c9d1d9',
  model_swap:  '#d2a8ff',
  agent_list:  '#30363d',
  step_info:   '#6e7681',
}

const LLM_TYPES = new Set(['thought', 'tool_call', 'tool_result'])

const typeColor = (t) => TYPE_COLOR[t] ?? '#8b949e'

function formatContent(type, content) {
  if (type === 'agent_list') return null
  if (type === 'tool_call' && typeof content === 'object') {
    const name = content.tool || '?'
    const args = content.args || {}
    const summary = Object.entries(args)
      .map(([k, v]) => {
        const s = typeof v === 'string' ? v : JSON.stringify(v)
        return `${k}=${s.length > 80 ? s.slice(0, 80) + '\u2026' : s}`
      })
      .join(', ')
    return `${name}(${summary})`
  }
  if (type === 'tool_result' && typeof content === 'object') {
    const name = content.tool || ''
    const result = typeof content.result === 'string'
      ? content.result
      : JSON.stringify(content.result, null, 2)
    const prefix = name ? `${name} \u2192 ` : ''
    return prefix + (result.length > 500 ? result.slice(0, 500) + '\u2026' : result)
  }
  if (content === null || content === undefined) return ''
  if (typeof content === 'object') {
    try { return JSON.stringify(content, null, 2) } catch { return String(content) }
  }
  return String(content)
}

function formatTime(ts) {
  try { return new Date(ts).toLocaleTimeString() } catch { return '' }
}

export default function LogStream({ logs }) {
  const topRef = useRef(null)
  const containerRef = useRef(null)
  const [expandedSteps, setExpandedSteps] = useState(new Set())

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const nearTop = el.scrollTop < 120
    if (nearTop) topRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const toggleStep = (key) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const visible = logs.filter((l) => l.type !== 'agent_list' && l.type !== 'thought_delta' && l.type !== 'thought_end').slice().reverse()

  return (
    <div ref={containerRef} style={container}>
      <div ref={topRef} />
      {visible.length === 0 && (
        <div style={emptyMsg}>Waiting for agent activity…</div>
      )}

      {visible.map((log, i) => {
        if (log.type === 'step_info' && typeof log.content === 'object') {
          const c = log.content
          if (c.event === 'start') {
            const stepKey = `${log.agent_id}-${c.step}`
            const expanded = expandedSteps.has(stepKey)
            const pct = c.history_max ? Math.round((c.history_messages / c.history_max) * 100) : 0
            const barColor = pct > 80 ? '#f85149' : pct > 50 ? '#d29922' : '#3fb950'
            const repeats = c.repeated_calls || {}
            const hasRepeats = Object.keys(repeats).length > 0
            return (
              <div key={i} style={stepDivider}>
                <div style={stepHeader}>
                  <span style={stepBadge}>STEP {c.step}</span>
                  <span style={stepModel}>{c.model}</span>
                  <span style={stepStat}>
                    ctx: {c.history_messages}/{c.history_max}
                    <span style={{ ...ctxBar, background: '#30363d', marginLeft: 6 }}>
                      <span style={{ ...ctxBarFill, width: `${Math.min(pct, 100)}%`, background: barColor }} />
                    </span>
                  </span>
                  <span style={stepStat}>~{c.est_tokens?.toLocaleString()} tok</span>
                  {hasRepeats && <span style={repeatWarn}>⚠ repeats</span>}
                  <button onClick={() => toggleStep(stepKey)} style={expandBtn}>
                    {expanded ? '▾ details' : '▸ details'}
                  </button>
                </div>
                {hasRepeats && (
                  <div style={repeatRow}>
                    {Object.entries(repeats).map(([call, count]) => (
                      <span key={call} style={repeatItem}>{call} ×{count}</span>
                    ))}
                  </div>
                )}
                {expanded && (
                  <div style={stepDetails}>
                    <div style={detailSection}>
                      <span style={detailLabel}>Roles:</span>
                      {Object.entries(c.roles || {}).map(([r, n]) => (
                        <span key={r} style={roleChip}>{r}: {n}</span>
                      ))}
                    </div>
                    <div style={detailSection}>
                      <span style={detailLabel}>System prompt:</span>
                    </div>
                    <pre style={promptPre}>{c.system_prompt}</pre>
                  </div>
                )}
              </div>
            )
          }
          if (c.event === 'end') {
            return (
              <div key={i} style={stepEnd}>
                <span style={stepEndText}>— step {c.step} done — ctx: {c.history_messages} msgs —</span>
              </div>
            )
          }
        }

        const content = formatContent(log.type, log.content)
        const isLLM = LLM_TYPES.has(log.type)
        return (
          <div key={i} style={isLLM ? llmRow : row}>
            <span style={timeCol}>{formatTime(log.timestamp)}</span>
            <span style={agentCol}>{log.agent_id || '—'}</span>
            <span style={typeTag(log.type)}>{log.type}</span>
            {content !== null && <span style={contentCol}>{content}</span>}
          </div>
        )
      })}

    </div>
  )
}

// ── styles ───────────────────────────────────────────────────────────────────

const container = {
  flex: 1,
  overflowY: 'auto',
  fontSize: 11.5,
  lineHeight: 1.55,
}

const emptyMsg = {
  padding: '40px 20px',
  color: '#484f58',
  textAlign: 'center',
}

const row = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  padding: '3px 16px',
  borderBottom: '1px solid #161b22',
}

const llmRow = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  padding: '3px 16px 3px 13px',
  borderBottom: '1px solid #161b22',
  borderLeft: '3px solid #58a6ff',
  background: '#58a6ff08',
}

const timeCol = {
  color: '#484f58',
  flexShrink: 0,
  fontSize: 10,
  paddingTop: 2,
  minWidth: 72,
}

const agentCol = {
  color: '#8b949e',
  flexShrink: 0,
  minWidth: 130,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const typeTag = (type) => ({
  flexShrink: 0,
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  color: typeColor(type),
  background: `${typeColor(type)}18`,
  borderRadius: 3,
  padding: '2px 6px',
  minWidth: 80,
  textAlign: 'center',
  alignSelf: 'flex-start',
  marginTop: 1,
})

const contentCol = {
  flex: 1,
  color: '#c9d1d9',
  wordBreak: 'break-word',
  whiteSpace: 'pre-wrap',
}

// ── step_info styles ─────────────────────────────────────────────────────────

const stepDivider = {
  padding: '8px 16px 6px',
  borderTop: '2px solid #30363d',
  borderBottom: '1px solid #21262d',
  background: '#161b2280',
  marginTop: 4,
}

const stepHeader = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  flexWrap: 'wrap',
}

const stepBadge = {
  fontSize: 10,
  fontWeight: 800,
  letterSpacing: 1,
  color: '#e6edf3',
  background: '#30363d',
  borderRadius: 3,
  padding: '2px 8px',
}

const stepModel = {
  fontSize: 10,
  color: '#d2a8ff',
}

const stepStat = {
  fontSize: 10,
  color: '#8b949e',
  display: 'flex',
  alignItems: 'center',
}

const ctxBar = {
  display: 'inline-block',
  width: 50,
  height: 6,
  borderRadius: 3,
  overflow: 'hidden',
}

const ctxBarFill = {
  display: 'block',
  height: '100%',
  borderRadius: 3,
  transition: 'width 0.3s',
}

const repeatWarn = {
  fontSize: 10,
  fontWeight: 700,
  color: '#d29922',
  background: '#d2992218',
  borderRadius: 3,
  padding: '2px 6px',
}

const expandBtn = {
  fontSize: 10,
  color: '#58a6ff',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  padding: '2px 4px',
  marginLeft: 'auto',
}

const repeatRow = {
  display: 'flex',
  gap: 8,
  flexWrap: 'wrap',
  marginTop: 4,
}

const repeatItem = {
  fontSize: 10,
  color: '#f0883e',
  background: '#f0883e14',
  borderRadius: 3,
  padding: '1px 6px',
  fontFamily: 'monospace',
}

const stepDetails = {
  marginTop: 6,
  paddingTop: 6,
  borderTop: '1px solid #21262d',
}

const detailSection = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
  marginBottom: 4,
}

const detailLabel = {
  fontSize: 10,
  color: '#6e7681',
  fontWeight: 600,
}

const roleChip = {
  fontSize: 10,
  color: '#8b949e',
  background: '#21262d',
  borderRadius: 3,
  padding: '1px 6px',
}

const promptPre = {
  fontSize: 10,
  color: '#8b949e',
  background: '#0d1117',
  border: '1px solid #21262d',
  borderRadius: 4,
  padding: '8px 10px',
  maxHeight: 200,
  overflowY: 'auto',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  margin: '4px 0 0',
}

const stepEnd = {
  textAlign: 'center',
  padding: '2px 16px',
  borderBottom: '1px solid #21262d',
}

const stepEndText = {
  fontSize: 9,
  color: '#484f58',
  letterSpacing: 0.5,
}
