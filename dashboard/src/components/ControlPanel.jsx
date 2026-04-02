import { useState, useEffect, useRef } from 'react'

const API = '/api/control'

export default function ControlPanel() {
  const [status, setStatus] = useState({ agents: [], models: [] })
  const [chatInput, setChatInput] = useState('')
  const [chatAgent, setChatAgent] = useState('')
  const [pullName, setPullName] = useState('')
  const [pulling, setPulling] = useState(false)
  const [pullMsg, setPullMsg] = useState('')
  // Spawn form
  const [spawnRole, setSpawnRole] = useState('assistant')
  const [spawnModel, setSpawnModel] = useState('')
  const [spawnGoal, setSpawnGoal] = useState('')
  const [spawnPrompt, setSpawnPrompt] = useState('')
  const [spawnId, setSpawnId] = useState('')
  const [spawnMode, setSpawnMode] = useState('chat')
  const [showSpawn, setShowSpawn] = useState(false)
  const timer = useRef(null)

  const refresh = () => {
    fetch(`${API}/status`)
      .then((r) => r.json())
      .then((d) => {
        setStatus(d)
        if (!chatAgent && d.agents?.length) setChatAgent(d.agents[0].agent_id)
        if (!spawnModel && d.models?.length) setSpawnModel(d.models[0].name)
      })
      .catch(() => {})
  }

  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 3000)
    return () => clearInterval(timer.current)
  }, [])

  const setMode = (agentId, mode) => {
    fetch(`${API}/mode`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ agent_id: agentId, mode }),
    }).then(refresh)
  }

  const setModel = (agentId, model) => {
    fetch(`${API}/model`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ agent_id: agentId, model }),
    }).then(refresh)
  }

  const killAgent = (agentId) => {
    fetch(`${API}/kill`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ agent_id: agentId, mode: '' }),
    }).then(refresh)
  }

  const spawnAgent = () => {
    fetch(`${API}/spawn`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({
        role: spawnRole, model: spawnModel, system_prompt: spawnPrompt,
        goal: spawnGoal, agent_id: spawnId, mode: spawnMode,
      }),
    }).then(() => {
      setShowSpawn(false)
      setSpawnGoal('')
      setSpawnPrompt('')
      setSpawnId('')
      refresh()
    })
  }

  const pullModel = () => {
    if (!pullName.trim()) return
    setPulling(true)
    setPullMsg(`Pulling ${pullName}…`)
    fetch(`${API}/pull`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ name: pullName.trim() }),
    })
      .then((r) => r.json())
      .then((d) => {
        setPullMsg(d.error || d.status || 'Done')
        setPulling(false)
        setPullName('')
        refresh()
      })
      .catch((e) => { setPullMsg(`Error: ${e}`); setPulling(false) })
  }

  const unloadModel = (name) => {
    fetch(`${API}/unload`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ name }),
    }).then(refresh)
  }

  const deleteModel = (name) => {
    if (!confirm(`Delete ${name} from disk?`)) return
    fetch(`${API}/delete_model`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ name }),
    }).then(refresh)
  }

  const sendStep = () => {
    if (!chatAgent) return
    fetch(`${API}/step?agent_id=${encodeURIComponent(chatAgent)}`, {
      method: 'POST', headers: CT,
      body: JSON.stringify({ message: chatInput }),
    }).then(() => { setChatInput(''); refresh() })
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendStep() }
  }

  const agents = status.agents || []
  const models = status.models || []
  const activeAgent = agents.find((a) => a.agent_id === chatAgent)
  const isChatMode = activeAgent?.mode === 'chat'

  return (
    <div style={container}>

      {/* ── Agents ────────────────────────────────── */}
      <div style={sectionRow}>
        <span style={sectionLabel}>Agents</span>
        <button style={spawnBtn} onClick={() => setShowSpawn(!showSpawn)}>
          {showSpawn ? '✕ Cancel' : '+ Spawn Agent'}
        </button>
      </div>

      {showSpawn && (
        <div style={spawnForm}>
          <div style={formGrid}>
            <label style={fLabel}>ID (optional)</label>
            <input style={fInput} value={spawnId} onChange={(e) => setSpawnId(e.target.value)} placeholder="auto-generated" />
            <label style={fLabel}>Role</label>
            <input style={fInput} value={spawnRole} onChange={(e) => setSpawnRole(e.target.value)} />
            <label style={fLabel}>Model</label>
            <select style={fSelect} value={spawnModel} onChange={(e) => setSpawnModel(e.target.value)}>
              {models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name} ({fmtSize(m.size)}){m.loaded ? ' ●' : ''}
                </option>
              ))}
            </select>
            <label style={fLabel}>Mode</label>
            <select style={fSelect} value={spawnMode} onChange={(e) => setSpawnMode(e.target.value)}>
              <option value="chat">Chat (paused)</option>
              <option value="auto">Auto (looping)</option>
            </select>
            <label style={fLabel}>Goal</label>
            <input style={fInput} value={spawnGoal} onChange={(e) => setSpawnGoal(e.target.value)} placeholder="Agent goal" />
            <label style={fLabel}>System prompt</label>
            <textarea style={{ ...fInput, minHeight: 50 }} value={spawnPrompt} onChange={(e) => setSpawnPrompt(e.target.value)} placeholder="Optional system prompt" />
          </div>
          <button style={goBtn} onClick={spawnAgent}>Spawn</button>
        </div>
      )}

      <div style={cardGrid}>
        {agents.map((a) => (
          <div key={a.agent_id} style={agentCard}>
            <div style={cardHeader}>
              <span style={agentName}>{a.agent_id}</span>
              <span style={roleBadge}>{a.role}</span>
              <span style={a.mode === 'chat' ? modeChatBadge : modeAutoBadge}>{a.mode}</span>
            </div>
            <div style={cardRow}>
              <span style={fieldLabel}>Model</span>
              <select style={selectStyle} value={a.model} onChange={(e) => setModel(a.agent_id, e.target.value)}>
                {models.map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name} ({fmtSize(m.size)}){m.loaded ? ' ●' : ''}
                  </option>
                ))}
                {!models.find((m) => m.name === a.model) && (
                  <option value={a.model}>{a.model}</option>
                )}
              </select>
            </div>
            <div style={cardRow}>
              <span style={fieldLabel}>Activity</span>
              <span style={activityText}>{a.activity}</span>
              <span style={stepCount}>step {a.step_count}</span>
            </div>
            <div style={cardActions}>
              <button style={a.mode === 'auto' ? btnActive : btn} onClick={() => setMode(a.agent_id, 'auto')}>▶ Auto</button>
              <button style={a.mode === 'chat' ? btnActiveChat : btn} onClick={() => setMode(a.agent_id, 'chat')}>⏸ Chat</button>
              <button style={btnDanger} onClick={() => killAgent(a.agent_id)}>✕ Kill</button>
            </div>
          </div>
        ))}
        {agents.length === 0 && <div style={emptyMsg}>No agents running</div>}
      </div>

      {/* ── Models ────────────────────────────────── */}
      <div style={sectionLabel}>Models</div>
      <div style={modelsSection}>
        <div style={pullRow}>
          <input
            style={pullInput}
            placeholder="Model name to download (e.g. mistral, codellama:13b, hf.co/user/repo:Q4_K_M)"
            value={pullName}
            onChange={(e) => setPullName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && pullModel()}
            disabled={pulling}
          />
          <button style={pulling ? sendBtnDisabled : goBtn} onClick={pullModel} disabled={pulling}>
            {pulling ? 'Pulling…' : 'Pull'}
          </button>
        </div>
        {pullMsg && <div style={pullMsgStyle}>{pullMsg}</div>}

        <table style={modelTable}>
          <thead>
            <tr>
              <th style={th}>Name</th>
              <th style={th}>Size</th>
              <th style={th}>Family</th>
              <th style={th}>Params</th>
              <th style={th}>Status</th>
              <th style={th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.name}>
                <td style={td}><span style={modelNameText}>{m.name}</span></td>
                <td style={td}>{fmtSize(m.size)}</td>
                <td style={td}>{m.family || '—'}</td>
                <td style={td}>{m.parameter_size || '—'}</td>
                <td style={td}>
                  {m.loaded
                    ? <span style={loadedBadge}>● loaded</span>
                    : <span style={unloadedBadge}>○ idle</span>}
                </td>
                <td style={td}>
                  {m.loaded && (
                    <button style={tblBtn} onClick={() => unloadModel(m.name)}>Unload</button>
                  )}
                  <button style={tblBtnDanger} onClick={() => deleteModel(m.name)}>Delete</button>
                </td>
              </tr>
            ))}
            {models.length === 0 && (
              <tr><td style={td} colSpan={6}>No models found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Chat ────────────────────────────────── */}
      <div style={sectionLabel}>Chat Mode</div>
      <div style={chatSection}>
        <div style={chatHeaderRow}>
          <select style={selectStyle} value={chatAgent} onChange={(e) => setChatAgent(e.target.value)}>
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>{a.agent_id} ({a.mode})</option>
            ))}
          </select>
          {!isChatMode && chatAgent && (
            <span style={chatHint}>Switch {chatAgent} to Chat mode first</span>
          )}
        </div>
        <div style={chatInputRow}>
          <textarea
            style={chatTextarea}
            placeholder={isChatMode ? 'Type a message and press Enter…' : 'Agent must be in Chat mode'}
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={handleKey}
            disabled={!isChatMode}
            rows={3}
          />
          <button style={isChatMode ? sendBtnGreen : sendBtnDisabled} onClick={sendStep} disabled={!isChatMode}>
            Send
          </button>
        </div>
        {isChatMode && (
          <div style={chatTip}>
            Each Send injects your message and triggers one model step. See results in Logs/Model Output.
          </div>
        )}
      </div>
    </div>
  )
}

// ── helpers ──────────────────────────────────────────────────────────────────

const CT = { 'Content-Type': 'application/json' }
const fmtSize = (bytes) => `${Math.round(bytes / (1024 ** 3) * 10) / 10}GB`

// ── styles ───────────────────────────────────────────────────────────────────

const container = { padding: '12px 16px', overflowY: 'auto', height: '100%' }

const sectionRow = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8,
}

const sectionLabel = {
  fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase',
  color: '#8b949e', marginBottom: 8, marginTop: 4,
}

const spawnBtn = {
  fontSize: 11, fontWeight: 600, padding: '4px 12px', borderRadius: 6,
  background: '#238636', color: '#fff', border: 'none', cursor: 'pointer',
}

const spawnForm = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '12px 16px', marginBottom: 12,
}

const formGrid = {
  display: 'grid', gridTemplateColumns: '100px 1fr', gap: '6px 10px', alignItems: 'start',
}

const fLabel = { fontSize: 10, color: '#8b949e', paddingTop: 5 }

const fInput = {
  background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '5px 8px', color: '#c9d1d9', fontSize: 11, fontFamily: 'inherit',
}

const fSelect = { ...fInput }

const goBtn = {
  padding: '6px 16px', background: '#238636', color: '#fff', border: 'none',
  borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 11, marginTop: 8,
}

const cardGrid = { display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 20 }

const agentCard = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '12px 16px', minWidth: 280, flex: '1 1 300px', maxWidth: 450,
}

const cardHeader = { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }
const agentName = { fontWeight: 700, color: '#e6edf3', fontSize: 13 }

const roleBadge = {
  fontSize: 9, fontWeight: 700, color: '#bc8cff', background: '#bc8cff18',
  borderRadius: 3, padding: '1px 6px', textTransform: 'uppercase',
}

const modeAutoBadge = {
  fontSize: 9, fontWeight: 700, color: '#3fb950', background: '#3fb95018',
  borderRadius: 3, padding: '1px 6px', marginLeft: 'auto',
}

const modeChatBadge = {
  fontSize: 9, fontWeight: 700, color: '#d29922', background: '#d2992218',
  borderRadius: 3, padding: '1px 6px', marginLeft: 'auto',
}

const cardRow = { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }
const fieldLabel = { fontSize: 10, color: '#6e7681', minWidth: 50, flexShrink: 0 }

const selectStyle = {
  background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '4px 8px', color: '#c9d1d9', fontSize: 11, flex: 1,
}

const activityText = { fontSize: 11, color: '#d29922', fontStyle: 'italic', flex: 1 }
const stepCount = { fontSize: 10, color: '#484f58' }

const cardActions = { display: 'flex', gap: 8, marginTop: 10 }

const btn = {
  flex: 1, padding: '6px 0', fontSize: 11, fontWeight: 600,
  background: '#21262d', color: '#8b949e', border: '1px solid #30363d',
  borderRadius: 6, cursor: 'pointer',
}

const btnActive = { ...btn, color: '#3fb950', background: '#3fb95014', borderColor: '#3fb950' }
const btnActiveChat = { ...btn, color: '#d29922', background: '#d2992214', borderColor: '#d29922' }

const btnDanger = {
  ...btn, flex: 'none', padding: '6px 12px', color: '#f85149',
  borderColor: '#f8514930', background: '#f8514910',
}

// Models section
const modelsSection = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '12px 16px', marginBottom: 20,
}

const pullRow = { display: 'flex', gap: 8, marginBottom: 8 }

const pullInput = {
  flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '6px 10px', color: '#c9d1d9', fontSize: 11, fontFamily: 'inherit',
}

const pullMsgStyle = { fontSize: 10, color: '#8b949e', marginBottom: 8 }

const modelTable = { width: '100%', borderCollapse: 'collapse', fontSize: 11 }
const th = {
  textAlign: 'left', color: '#8b949e', fontWeight: 600, fontSize: 10,
  padding: '4px 8px', borderBottom: '1px solid #21262d', textTransform: 'uppercase',
  letterSpacing: 0.5,
}
const td = { padding: '6px 8px', borderBottom: '1px solid #161b22', color: '#c9d1d9' }

const modelNameText = { fontWeight: 600 }

const loadedBadge = { color: '#3fb950', fontSize: 10 }
const unloadedBadge = { color: '#484f58', fontSize: 10 }

const tblBtn = {
  fontSize: 10, padding: '2px 8px', background: '#21262d', color: '#8b949e',
  border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer', marginRight: 4,
}

const tblBtnDanger = {
  ...tblBtn, color: '#f85149', borderColor: '#f8514930',
}

// Chat
const chatSection = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '12px 16px',
}

const chatHeaderRow = { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }
const chatHint = { fontSize: 10, color: '#d29922', fontStyle: 'italic' }
const chatInputRow = { display: 'flex', gap: 8 }

const chatTextarea = {
  flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
  padding: '8px 12px', color: '#c9d1d9', fontSize: 12, resize: 'vertical',
  fontFamily: 'inherit', outline: 'none', lineHeight: 1.4,
}

const sendBtnGreen = {
  padding: '8px 20px', background: '#238636', color: '#fff', border: 'none',
  borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12, alignSelf: 'flex-end',
}

const sendBtnDisabled = {
  ...sendBtnGreen, background: '#21262d', color: '#484f58', cursor: 'not-allowed',
}

const chatTip = { fontSize: 10, color: '#484f58', marginTop: 8, lineHeight: 1.4 }
const emptyMsg = { padding: '20px', color: '#484f58', fontSize: 12 }
