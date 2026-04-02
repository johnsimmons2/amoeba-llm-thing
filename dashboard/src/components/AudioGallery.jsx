import { useState, useEffect, useRef } from 'react'

const CT = { 'Content-Type': 'application/json' }

export default function AudioGallery() {
  const [clips, setClips] = useState([])
  const [pipeStatus, setPipeStatus] = useState({})
  const [models, setModels] = useState([])
  const [playing, setPlaying] = useState(null)
  const [selectedClip, setSelectedClip] = useState(null)
  // Generate form
  const [prompt, setPrompt] = useState('')
  const [duration, setDuration] = useState(10)
  const [guidance, setGuidance] = useState(3.0)
  const [generating, setGenerating] = useState(false)
  const [genMsg, setGenMsg] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [customModel, setCustomModel] = useState('')
  const [loadingModel, setLoadingModel] = useState(false)
  const [fileName, setFileName] = useState('')
  const [genBatch, setGenBatch] = useState(1)
  const [addSource, setAddSource] = useState('huggingface')
  const [ollamaModel, setOllamaModel] = useState('')
  const [civitaiModel, setCivitaiModel] = useState('')
  const audioRef = useRef(null)
  const timer = useRef(null)

  const refresh = () => {
    fetch('/api/audio').then(r => r.json()).then(setClips).catch(() => {})
    fetch('/api/audio_gen/status').then(r => r.json()).then(setPipeStatus).catch(() => {})
    fetch('/api/audio_gen/models').then(r => r.json()).then(d => {
      setModels(d)
    }).catch(() => {})
  }

  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 5000)
    return () => clearInterval(timer.current)
  }, [])

  const unload = () => {
    fetch('/api/audio_gen/unload', { method: 'POST' }).then(refresh)
  }

  const addCustomModel = () => {
    const name = customModel.trim()
    if (!name || models.some(m => m.name === name)) return
    fetch('/api/audio_gen/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name, source: 'huggingface' }),
    }).then(() => { setCustomModel(''); refresh() })
  }

  const addOllamaAudio = () => {
    const name = ollamaModel.trim()
    if (!name || models.some(m => m.name === name)) return
    fetch('/api/audio_gen/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name, source: 'ollama' }),
    }).then(() => { setOllamaModel(''); refresh() })
  }

  const addCivitaiAudio = () => {
    const name = civitaiModel.trim()
    if (!name || models.some(m => m.name === name)) return
    fetch('/api/audio_gen/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name, source: 'civitai' }),
    }).then(() => { setCivitaiModel(''); refresh() })
  }

  const loadModel = (name) => {
    if (loadingModel) return
    setLoadingModel(true)
    setGenMsg(`Loading pipeline: ${name}…`)
    fetch('/api/audio_gen/load', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name }),
    })
      .then(r => r.json())
      .then(d => {
        setGenMsg(d.error ? `Error: ${d.error}` : d.status)
        setLoadingModel(false)
        refresh()
      })
      .catch(e => { setGenMsg(`Error: ${e}`); setLoadingModel(false) })
  }

  const generate = () => {
    if (!prompt.trim() || generating || !pipeStatus.pipeline_loaded) return
    setGenerating(true)
    setGenMsg(`Generating${genBatch > 1 ? ` (${genBatch} clips)` : ''}…`)
    fetch('/api/audio_gen/generate', {
      method: 'POST', headers: CT,
      body: JSON.stringify({
        prompt: prompt.trim(),
        model: pipeStatus.loaded_model,
        duration,
        guidance_scale: guidance,
        filename: fileName.trim(),
        batch_count: genBatch,
      }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) setGenMsg(`Error: ${d.error}`)
        else {
          const names = d.clips.map(c => c.filename).join(', ')
          setGenMsg(`Done — ${d.count} clip${d.count > 1 ? 's' : ''}: ${names}`)
        }
        setGenerating(false)
        refresh()
      })
      .catch(e => { setGenMsg(`Error: ${e}`); setGenerating(false) })
  }

  const play = (clip) => {
    if (playing === clip.filename) {
      audioRef.current?.pause()
      setPlaying(null)
    } else {
      setPlaying(clip.filename)
      setTimeout(() => audioRef.current?.play(), 50)
    }
  }

  return (
    <div style={container}>
      {/* Pipeline status */}
      <div style={statusBar}>
        <span style={sectionLabel}>Audio Pipeline</span>
        {pipeStatus.pipeline_loaded ? (
          <>
            <span style={loadedBadge}>● {pipeStatus.loaded_model}</span>
            <span style={typeBadge}>{pipeStatus.pipeline_type}</span>
            <button style={unloadBtn} onClick={unload}>Unload (free VRAM)</button>
          </>
        ) : (
          <span style={idleBadge}>○ No model loaded</span>
        )}
      </div>

      {/* Generate form */}
      <div style={genSection}>
        <div style={genTopRow}>
          <textarea
            style={promptInput}
            placeholder="Describe the audio (e.g. 'upbeat electronic dance music with heavy bass')"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); generate() } }}
            disabled={generating}
            rows={2}
          />
          <button
            style={generating || !pipeStatus.pipeline_loaded ? genBtnDisabled : genBtn}
            onClick={generate}
            disabled={generating || !pipeStatus.pipeline_loaded}
          >
            {generating ? '⏳' : !pipeStatus.pipeline_loaded ? '♫ No model' : '♫ Generate'}
          </button>
        </div>
        <div style={genOptionsRow}>
          <input
            style={fileNameInput}
            value={fileName}
            onChange={e => setFileName(e.target.value)}
            placeholder="filename (optional, auto-generated if empty)"
            disabled={generating}
          />
          <button style={advToggle} onClick={() => setShowAdvanced(!showAdvanced)}>
            {showAdvanced ? '▾ Less' : '▸ Options'}
          </button>
        </div>
        {showAdvanced && (
          <div style={advancedGrid}>
            <label style={advLabel}>Duration (s)</label>
            <input style={advInput} type="number" value={duration} onChange={e => setDuration(+e.target.value)} min={1} max={60} step={1} />
            <label style={advLabel}>Guidance</label>
            <input style={advInput} type="number" value={guidance} onChange={e => setGuidance(+e.target.value)} min={0} max={20} step={0.5} />
            <label style={advLabel}>Batch Count</label>
            <input style={advInput} type="number" value={genBatch} onChange={e => setGenBatch(Math.max(1, Math.min(20, +e.target.value)))} min={1} max={20} title="Number of clips to generate" />
          </div>
        )}
        {genMsg && <div style={genMsgStyle}>{genMsg}</div>}
      </div>

      {/* Model selector panel */}
      <div style={modelPanel}>
        <div style={modelPanelHeader}>
          <span style={sectionLabel}>Models</span>
        </div>
        <div style={addModelSection}>
          <div style={sourceToggle}>
            <button style={addSource === 'huggingface' ? srcActive : srcBtn} onClick={() => setAddSource('huggingface')}>HuggingFace</button>
            <button style={addSource === 'civitai' ? srcActive : srcBtn} onClick={() => setAddSource('civitai')}>CivitAI</button>
            <button style={addSource === 'ollama' ? srcActive : srcBtn} onClick={() => setAddSource('ollama')}>Ollama</button>
          </div>

          {addSource === 'huggingface' && (
            <div style={addModelRow}>
              <input
                style={addModelInput}
                value={customModel}
                onChange={e => setCustomModel(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') addCustomModel() }}
                placeholder="org/model-name (e.g. facebook/musicgen-small)"
              />
              <button style={addModelBtn} onClick={addCustomModel} disabled={!customModel.trim()}>+ Add</button>
            </div>
          )}

          {addSource === 'civitai' && (
            <div>
              <div style={addModelRow}>
                <input
                  style={addModelInput}
                  value={civitaiModel}
                  onChange={e => setCivitaiModel(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') addCivitaiAudio() }}
                  placeholder="CivitAI model name or URL"
                />
                <button style={addModelBtn} onClick={addCivitaiAudio} disabled={!civitaiModel.trim()}>+ Add</button>
              </div>
              <div style={sourceNote}>CivitAI audio model support is limited. Most audio models are hosted on HuggingFace.</div>
            </div>
          )}

          {addSource === 'ollama' && (
            <div>
              <div style={addModelRow}>
                <input
                  style={addModelInput}
                  value={ollamaModel}
                  onChange={e => setOllamaModel(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') addOllamaAudio() }}
                  placeholder="Ollama model name (e.g. model:tag)"
                />
                <button style={addModelBtn} onClick={addOllamaAudio} disabled={!ollamaModel.trim()}>+ Add</button>
              </div>
              <div style={sourceNote}>Ollama-sourced audio models are experimental. Model must be compatible with the audio pipeline to load successfully.</div>
            </div>
          )}
        </div>
        <div style={modelList}>
          {models.map(m => (
            <div key={m.name} style={m.loaded ? mlRowActive : mlRow}>
              <div style={mlInfo}>
                <span style={mlName}>{m.name}</span>
                <span style={mlDesc}>
                  {m.description && m.description !== 'Custom model' ? m.description : ''} {m.vram ? `· ${m.vram}` : ''}
                </span>
              </div>
              <div style={mlBadges}>
                {m.downloaded
                  ? <span style={dlBadge}>downloaded</span>
                  : <span style={notDlBadge}>not downloaded</span>}
                {m.loaded && <span style={loadedModelBadge}>● loaded</span>}
              </div>
              <div style={mlActions}>
                {!m.downloaded && !m.loaded && (
                  <button
                    style={downloadBtn}
                    onClick={() => loadModel(m.name)}
                    disabled={loadingModel}
                  >
                    {loadingModel ? '…' : '⬇ Download'}
                  </button>
                )}
                {m.downloaded && !m.loaded && (
                  <button
                    style={swapBtn}
                    onClick={() => loadModel(m.name)}
                    disabled={loadingModel}
                  >
                    {loadingModel ? '…' : '⇄ Swap to'}
                  </button>
                )}
                {m.loaded && (
                  <button
                    style={swapUnloadBtn}
                    onClick={() => unload()}
                  >
                    Unload
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Audio list */}
      <div style={sectionLabel}>Generated Audio ({clips.length})</div>

      {clips.length === 0 ? (
        <div style={emptyMsg}>
          No audio yet. Type a prompt above or let agents use the <code>generate_audio</code> tool.
        </div>
      ) : (
        <div style={clipList}>
          {clips.map(c => (
            <div key={c.filename} style={clipCard} onClick={() => setSelectedClip(selectedClip?.filename === c.filename ? null : c)}>
              <button style={playBtn} onClick={e => { e.stopPropagation(); play(c) }}>
                {playing === c.filename ? '⏸' : '▶'}
              </button>
              <div style={clipInfo}>
                <span style={clipName}>{c.meta?.prompt ? c.meta.prompt.slice(0, 80) + (c.meta.prompt.length > 80 ? '…' : '') : c.filename}</span>
                <span style={clipSize}>
                  {c.duration != null ? `${c.duration}s` : '?'} · {fmtSize(c.size)} · {c.filename}
                </span>
              </div>
              <a href={c.url} download style={dlLink} title="Download" onClick={e => e.stopPropagation()}>⬇</a>
            </div>
          ))}
        </div>
      )}

      {/* Detail panel for selected clip */}
      {selectedClip && selectedClip.meta && (
        <div style={audioMetaPanel}>
          <div style={audioMetaHeader}>
            <span style={{fontWeight:600,color:'#c9d1d9',fontSize:12}}>{selectedClip.filename}</span>
            <button style={audioMetaClose} onClick={() => setSelectedClip(null)}>✕</button>
          </div>
          <div style={audioMetaBody}>
            <span style={audioMetaLabel}>Prompt</span>
            <span style={audioMetaVal}>{selectedClip.meta.prompt}</span>
            <span style={audioMetaLabel}>Model</span>
            <span style={audioMetaVal}>{selectedClip.meta.model}</span>
            <span style={audioMetaLabel}>Duration</span>
            <span style={audioMetaVal}>{selectedClip.meta.duration}s</span>
            <span style={audioMetaLabel}>Guidance</span>
            <span style={audioMetaVal}>{selectedClip.meta.guidance_scale}</span>
            <span style={audioMetaLabel}>Sample Rate</span>
            <span style={audioMetaVal}>{selectedClip.meta.sample_rate} Hz</span>
            <span style={audioMetaLabel}>Pipeline</span>
            <span style={audioMetaVal}>{selectedClip.meta.pipeline_type}</span>
          </div>
        </div>
      )}

      {/* Hidden audio player */}
      {playing && (
        <audio
          ref={audioRef}
          src={clips.find(c => c.filename === playing)?.url}
          onEnded={() => setPlaying(null)}
        />
      )}
    </div>
  )
}

const fmtSize = (bytes) => {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

// Styles
const container = { padding: '12px 16px', overflowY: 'auto', height: '100%' }

const statusBar = {
  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
  padding: '8px 14px', background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
}

const sectionLabel = {
  fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase',
  color: '#8b949e', marginBottom: 8,
}

const loadedBadge = { color: '#3fb950', fontSize: 11, fontWeight: 600 }
const idleBadge = { color: '#484f58', fontSize: 11 }
const typeBadge = {
  fontSize: 9, fontWeight: 700, color: '#bc8cff', background: '#bc8cff18',
  borderRadius: 3, padding: '1px 6px', textTransform: 'uppercase',
}

const unloadBtn = {
  marginLeft: 'auto', fontSize: 10, padding: '3px 10px',
  background: '#21262d', color: '#f85149', border: '1px solid #f8514930',
  borderRadius: 4, cursor: 'pointer',
}

// Model panel styles
const modelPanel = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '10px 14px', marginBottom: 16,
}

const modelPanelHeader = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  gap: 12, marginBottom: 8,
}

const addModelRow = { display: 'flex', gap: 6, flex: 1, maxWidth: 400 }

const addModelInput = {
  flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '4px 8px', color: '#c9d1d9', fontSize: 11, fontFamily: 'inherit',
}

const addModelBtn = {
  fontSize: 10, padding: '4px 10px', background: '#21262d', color: '#58a6ff',
  border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap',
}

const addModelSection = { marginBottom: 8 }

const sourceToggle = { display: 'flex', gap: 2, marginBottom: 8 }

const srcBtn = {
  fontSize: 10, padding: '4px 12px', background: '#21262d', color: '#8b949e',
  border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer',
}

const srcActive = {
  ...srcBtn, color: '#58a6ff', border: '1px solid #58a6ff60', background: '#58a6ff12',
}

const sourceNote = {
  fontSize: 10, color: '#8b949e', marginTop: 4, fontStyle: 'italic',
}

const modelList = { display: 'flex', flexDirection: 'column', gap: 4 }

const mlRow = {
  display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px',
  borderRadius: 6, cursor: 'pointer', transition: 'background 0.15s',
  border: '1px solid transparent',
}

const mlRowActive = {
  ...mlRow, background: '#58a6ff10', border: '1px solid #58a6ff40',
}

const mlInfo = { flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }

const mlName = {
  fontSize: 11, color: '#c9d1d9', fontWeight: 600, fontFamily: 'monospace',
  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
}

const mlDesc = { fontSize: 10, color: '#6e7681' }

const mlBadges = { display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }

const dlBadge = {
  fontSize: 8, fontWeight: 700, color: '#3fb950', background: '#3fb95018',
  borderRadius: 3, padding: '1px 6px', textTransform: 'uppercase',
}

const notDlBadge = {
  fontSize: 8, fontWeight: 700, color: '#6e7681', background: '#6e768118',
  borderRadius: 3, padding: '1px 6px', textTransform: 'uppercase',
}

const loadedModelBadge = {
  fontSize: 8, fontWeight: 700, color: '#3fb950',
}

const mlActions = { display: 'flex', gap: 4, flexShrink: 0 }

const downloadBtn = {
  fontSize: 9, padding: '3px 8px', background: '#1f6feb', color: '#fff',
  border: 'none', borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap',
}

const swapBtn = {
  fontSize: 9, padding: '3px 8px', background: '#238636', color: '#fff',
  border: 'none', borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap',
}

const swapUnloadBtn = {
  fontSize: 9, padding: '3px 8px', background: '#21262d', color: '#f85149',
  border: '1px solid #f8514930', borderRadius: 4, cursor: 'pointer', whiteSpace: 'nowrap',
}

const genSection = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '12px 16px', marginBottom: 16,
}

const genTopRow = { display: 'flex', gap: 8 }

const promptInput = {
  flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
  padding: '8px 12px', color: '#c9d1d9', fontSize: 12, resize: 'vertical',
  fontFamily: 'inherit', outline: 'none', lineHeight: 1.4,
}

const genBtn = {
  padding: '8px 20px', background: '#238636', color: '#fff', border: 'none',
  borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12, alignSelf: 'flex-end',
  whiteSpace: 'nowrap',
}

const genBtnDisabled = { ...genBtn, background: '#21262d', color: '#484f58', cursor: 'wait' }

const genOptionsRow = { display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }

const fileNameInput = {
  flex: 1, background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '4px 8px', color: '#c9d1d9', fontSize: 11, fontFamily: 'inherit',
}

const advToggle = {
  fontSize: 10, color: '#8b949e', background: 'transparent', border: 'none',
  cursor: 'pointer', padding: '4px 8px',
}

const advancedGrid = {
  display: 'grid', gridTemplateColumns: '100px 1fr', gap: '4px 8px',
  marginTop: 8, alignItems: 'center',
}

const advLabel = { fontSize: 10, color: '#6e7681' }

const advInput = {
  background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '4px 8px', color: '#c9d1d9', fontSize: 11, fontFamily: 'inherit',
}

const genMsgStyle = { fontSize: 10, color: '#8b949e', marginTop: 8 }

const clipList = { display: 'flex', flexDirection: 'column', gap: 6 }

const clipCard = {
  display: 'flex', alignItems: 'center', gap: 10,
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '8px 14px',
}

const playBtn = {
  width: 32, height: 32, borderRadius: '50%', border: '1px solid #30363d',
  background: '#21262d', color: '#58a6ff', fontSize: 14,
  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
  flexShrink: 0,
}

const clipInfo = { flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }
const clipName = {
  fontSize: 11, color: '#c9d1d9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
}
const clipSize = { fontSize: 10, color: '#484f58', fontFamily: 'monospace' }

const dlLink = {
  color: '#8b949e', textDecoration: 'none', fontSize: 14, padding: '4px 8px',
}

// Audio metadata detail panel
const audioMetaPanel = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '10px 14px', marginBottom: 12,
}

const audioMetaHeader = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8,
}

const audioMetaClose = {
  fontSize: 10, background: 'transparent', border: 'none', color: '#8b949e',
  cursor: 'pointer', padding: '2px 6px',
}

const audioMetaBody = {
  display: 'grid', gridTemplateColumns: '90px 1fr', gap: '2px 8px', fontSize: 10,
}

const audioMetaLabel = {
  fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: '#8b949e',
}

const audioMetaVal = {
  color: '#c9d1d9', fontFamily: 'monospace', wordBreak: 'break-word',
}

const emptyMsg = {
  padding: 40, textAlign: 'center', color: '#484f58', fontSize: 12, lineHeight: 1.6,
}
