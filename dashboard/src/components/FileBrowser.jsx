import { useState, useEffect } from 'react'

function ageColor(mtime) {
  const age = (Date.now() / 1000) - mtime
  if (age < 300) return '#3fb950'
  if (age < 3600) return '#58a6ff'
  if (age < 86400) return '#d29922'
  return '#8b949e'
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

function buildTree(files) {
  const root = { name: '', children: {}, files: [] }
  for (const f of files) {
    const parts = f.path.split('/')
    let node = root
    for (let i = 0; i < parts.length - 1; i++) {
      if (!node.children[parts[i]]) {
        node.children[parts[i]] = { name: parts[i], children: {}, files: [] }
      }
      node = node.children[parts[i]]
    }
    node.files.push({ ...f, name: parts[parts.length - 1] })
  }
  return root
}

function TreeNode({ node, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2)
  const dirs = Object.values(node.children).sort((a, b) => a.name.localeCompare(b.name))
  const files = [...node.files].sort((a, b) => a.name.localeCompare(b.name))

  return (
    <div style={{ paddingLeft: depth ? 14 : 0 }}>
      {node.name && (
        <div style={dirRow} onClick={() => setOpen(!open)}>
          <span style={chevron}>{open ? '▾' : '▸'}</span>
          <span style={dirName}>{node.name}/</span>
        </div>
      )}
      {(open || !node.name) && (
        <>
          {dirs.map((d) => (
            <TreeNode key={d.name} node={d} depth={depth + 1} />
          ))}
          {files.map((f) => (
            <div key={f.name} style={fileRow}>
              <span style={{ color: ageColor(f.modified) }}>{f.name}</span>
              <span style={sizeLabel}>{formatSize(f.size)}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

export default function FileBrowser() {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchFiles = async () => {
    try {
      const res = await fetch('/api/files')
      setFiles(await res.json())
    } catch { /* ignore */ }
    setLoading(false)
  }

  useEffect(() => { fetchFiles() }, [])
  useEffect(() => {
    const id = setInterval(fetchFiles, 10000)
    return () => clearInterval(id)
  }, [])

  if (loading) return <div style={emptyMsg}>Loading files…</div>
  if (files.length === 0) return <div style={emptyMsg}>No files found.</div>

  const tree = buildTree(files)

  return (
    <div style={container}>
      <div style={legend}>
        <span style={{ color: '#3fb950' }}>●</span> &lt;5m
        <span style={{ color: '#58a6ff', marginLeft: 10 }}>●</span> &lt;1h
        <span style={{ color: '#d29922', marginLeft: 10 }}>●</span> &lt;24h
        <span style={{ color: '#8b949e', marginLeft: 10 }}>●</span> older
      </div>
      <TreeNode node={tree} />
    </div>
  )
}

// ── styles ───────────────────────────────────────────────────────────────────

const container = { flex: 1, overflowY: 'auto', padding: 16, fontSize: 12 }
const emptyMsg = { padding: '40px 20px', color: '#484f58', textAlign: 'center' }
const legend = { fontSize: 10, color: '#8b949e', marginBottom: 12 }
const chevron = { color: '#8b949e', fontSize: 10, marginRight: 4, width: 10, display: 'inline-block' }
const dirRow = { display: 'flex', alignItems: 'center', padding: '2px 0', cursor: 'pointer', userSelect: 'none' }
const dirName = { color: '#58a6ff', fontWeight: 600 }
const fileRow = { display: 'flex', alignItems: 'center', gap: 8, padding: '1px 0', paddingLeft: 14, fontSize: 11.5 }
const sizeLabel = { color: '#484f58', fontSize: 10, flexShrink: 0 }
const timeLabel = { color: '#6e7681', fontSize: 10, flexShrink: 0, marginLeft: 'auto' }
