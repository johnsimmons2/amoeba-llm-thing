const ROLE_COLOR = {
  coordinator: '#f0883e',
  researcher:  '#58a6ff',
  coder:       '#3fb950',
  analyst:     '#d2a8ff',
  writer:      '#79c0ff',
}

const roleColor = (role) => ROLE_COLOR[role] ?? '#8b949e'

export default function AgentList({ agents }) {
  return (
    <div>
      <div style={sectionHeading}>Agents</div>

      {agents.length === 0 && (
        <div style={emptyMsg}>Waiting for agents…</div>
      )}

      {agents.map((a) => (
        <div key={a.agent_id} style={card}>
          <div style={cardRow}>
            <div style={statusDot(a.running)} title={a.running ? 'running' : 'stopped'} />
            <span style={agentId}>{a.agent_id}</span>
          </div>
          <div style={cardMeta}>
            <span style={roleTag(a.role)}>{a.role}</span>
          </div>
          <div style={modelRow}>
            <span style={modelIcon}>◆</span>
            <span style={modelName}>{a.model}</span>
          </div>          {a.activity && a.activity !== 'idle' && (
            <div style={activityRow}>
              <span style={activityDot}>\u25CF</span>
              <span style={activityText}>{a.activity}</span>
            </div>
          )}        </div>
      ))}
    </div>
  )
}

// ── styles ──────────────────────────────────────────────────────────────────

const sectionHeading = {
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 1.5,
  color: '#8b949e',
  textTransform: 'uppercase',
  marginBottom: 10,
}

const emptyMsg = {
  fontSize: 11,
  color: '#484f58',
  textAlign: 'center',
  marginTop: 20,
}

const card = {
  background: '#161b22',
  border: '1px solid #21262d',
  borderRadius: 6,
  padding: '8px 10px',
  marginBottom: 6,
}

const cardRow = {
  display: 'flex',
  alignItems: 'center',
  gap: 7,
  marginBottom: 4,
}

const statusDot = (running) => ({
  width: 7,
  height: 7,
  borderRadius: '50%',
  background: running ? '#3fb950' : '#484f58',
  flexShrink: 0,
})

const agentId = {
  fontSize: 11,
  fontWeight: 600,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: '#e6edf3',
}

const cardMeta = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  marginBottom: 4,
}

const roleTag = (role) => ({
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0.5,
  textTransform: 'uppercase',
  color: roleColor(role),
  background: `${roleColor(role)}22`,
  borderRadius: 3,
  padding: '1px 5px',
})

const modelRow = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  marginTop: 2,
}

const modelIcon = {
  fontSize: 8,
  color: '#d2a8ff',
}

const modelName = {
  fontSize: 10,
  fontWeight: 600,
  color: '#d2a8ff',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const activityRow = {
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  marginTop: 4,
}

const activityDot = {
  fontSize: 7,
  color: '#d29922',
}

const activityText = {
  fontSize: 10,
  color: '#d29922',
  fontStyle: 'italic',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}
