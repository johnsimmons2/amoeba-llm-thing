import { useState, useEffect, useRef } from 'react'
import AgentList from './components/AgentList.jsx'
import LogStream from './components/LogStream.jsx'
import ModelOutput from './components/ModelOutput.jsx'
import FileBrowser from './components/FileBrowser.jsx'
import DbExplorer from './components/DbExplorer.jsx'
import TaskBoard from './components/TaskBoard.jsx'
import NotesBrowser from './components/NotesBrowser.jsx'
import ControlPanel from './components/ControlPanel.jsx'
import ImageGallery from './components/ImageGallery.jsx'
import AudioGallery from './components/AudioGallery.jsx'

const WS_URL = `ws://${window.location.hostname}:8000/ws/logs`

const TABS = [
  { id: 'control', label: 'Control' },
  { id: 'logs', label: 'Logs' },
  { id: 'output', label: 'Model Output' },
  { id: 'images', label: 'Images' },
  { id: 'audio', label: 'Audio' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'notes', label: 'Notes' },
  { id: 'files', label: 'Files' },
  { id: 'db', label: 'Database' },
]

const css = {
  app: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 18px',
    borderBottom: '1px solid #21262d',
    flexShrink: 0,
  },
  logo: {
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: 2,
    color: '#58a6ff',
    textTransform: 'uppercase',
    userSelect: 'none',
  },
  dot: (ok) => ({
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: ok ? '#3fb950' : '#f85149',
    transition: 'background 0.3s',
  }),
  connLabel: {
    fontSize: 10,
    color: '#8b949e',
  },
  tabBar: {
    display: 'flex',
    gap: 2,
    marginLeft: 16,
    background: '#161b22',
    borderRadius: 6,
    padding: 2,
  },
  tab: {
    fontSize: 11,
    fontWeight: 500,
    fontFamily: 'inherit',
    color: '#8b949e',
    background: 'transparent',
    border: 'none',
    borderRadius: 4,
    padding: '4px 12px',
    cursor: 'pointer',
  },
  tabActive: {
    fontSize: 11,
    fontWeight: 600,
    fontFamily: 'inherit',
    color: '#e6edf3',
    background: '#30363d',
    border: 'none',
    borderRadius: 4,
    padding: '4px 12px',
    cursor: 'pointer',
  },
  body: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  sidebar: {
    width: 270,
    flexShrink: 0,
    borderRight: '1px solid #21262d',
    overflowY: 'auto',
    padding: 12,
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
}

export default function App() {
  const [logs, setLogs] = useState([])
  const [agents, setAgents] = useState([])
  const [connected, setConnected] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [activeTab, setActiveTab] = useState('logs')

  // WebSocket — auto-reconnect
  useEffect(() => {
    let ws
    let reconnectTimer
    let alive = true

    const connect = () => {
      ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setConnected(true)
        setLogs([])  // clear stale logs; server replays history
      }

      ws.onclose = () => {
        setConnected(false)
        if (alive) reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'agent_list') {
            setAgents(msg.content || [])
          } else {
            setLogs((prev) => {
              const next = [...prev, msg]
              return next.length > 1000 ? next.slice(-1000) : next
            })
          }
        } catch { /* ignore malformed frames */ }
      }
    }

    connect()
    return () => {
      alive = false
      clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])

  const sendChat = async () => {
    const text = chatInput.trim()
    if (!text) return
    setChatInput('')
    try {
      await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
    } catch (err) {
      console.error('Send chat failed:', err)
    }
  }

  return (
    <div style={css.app}>
      <header style={css.header}>
        <span style={css.logo}>⬡ AI Sandbox</span>
        <div style={css.dot(connected)} title={connected ? 'Connected' : 'Disconnected'} />
        <span style={css.connLabel}>{connected ? 'live' : 'reconnecting…'}</span>

        <div style={css.tabBar}>
          {TABS.map((t) => (
            <button
              key={t.id}
              style={activeTab === t.id ? css.tabActive : css.tab}
              onClick={() => setActiveTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <span style={{ ...css.connLabel, marginLeft: 'auto' }}>
          {agents.length} agent{agents.length !== 1 ? 's' : ''}
        </span>
      </header>

      <div style={css.body}>
        <aside style={css.sidebar}>
          <AgentList agents={agents} />
        </aside>

        <main style={css.main}>
          {activeTab === 'control' && <ControlPanel />}
          {activeTab === 'logs' && <LogStream logs={logs} />}
          {activeTab === 'output' && <ModelOutput logs={logs} />}
          {activeTab === 'images' && <ImageGallery />}
          {activeTab === 'audio' && <AudioGallery />}
          {activeTab === 'tasks' && <TaskBoard />}
          {activeTab === 'notes' && <NotesBrowser />}
          {activeTab === 'files' && <FileBrowser />}
          {activeTab === 'db' && <DbExplorer />}
          {activeTab !== 'files' && activeTab !== 'db' && activeTab !== 'tasks' && activeTab !== 'notes' && activeTab !== 'control' && activeTab !== 'images' && activeTab !== 'audio' && (
            <ChatBar value={chatInput} onChange={setChatInput} onSend={sendChat} />
          )}
        </main>
      </div>
    </div>
  )
}

function ChatBar({ value, onChange, onSend }) {
  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div style={{
      display: 'flex',
      gap: 8,
      padding: '10px 14px',
      borderTop: '1px solid #21262d',
      flexShrink: 0,
    }}>
      <input
        style={{
          flex: 1,
          background: '#161b22',
          border: '1px solid #30363d',
          borderRadius: 6,
          color: '#e6edf3',
          padding: '7px 12px',
          fontFamily: 'inherit',
          fontSize: 12,
          outline: 'none',
        }}
        placeholder="Send a message to all agents…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
      />
      <button
        style={{
          background: '#238636',
          border: 'none',
          borderRadius: 6,
          color: '#fff',
          padding: '7px 16px',
          cursor: 'pointer',
          fontSize: 12,
          fontFamily: 'inherit',
        }}
        onClick={onSend}
      >
        Send
      </button>
    </div>
  )
}
