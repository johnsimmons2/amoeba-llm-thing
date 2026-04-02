import { useState, useEffect, useRef } from 'react'

const CT = { 'Content-Type': 'application/json' }

export default function ImageGallery() {
  const [images, setImages] = useState([])
  const [diffStatus, setDiffStatus] = useState({})
  const [models, setModels] = useState([])
  const [selected, setSelected] = useState(null)
  // Generate form
  const [prompt, setPrompt] = useState('')
  const [negPrompt, setNegPrompt] = useState('')
  const [genWidth, setGenWidth] = useState(1024)
  const [genHeight, setGenHeight] = useState(1024)
  const [genSteps, setGenSteps] = useState(20)
  const [genGuidance, setGenGuidance] = useState(7.5)
  const [genClipSkip, setGenClipSkip] = useState(0)
  const [genSeed, setGenSeed] = useState(-1)
  const [genBatch, setGenBatch] = useState(1)
  const [generating, setGenerating] = useState(false)
  const [genMsg, setGenMsg] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [customModel, setCustomModel] = useState('')
  const [loading, setLoading] = useState(false)
  const [addSource, setAddSource] = useState('huggingface')
  const [addMode, setAddMode] = useState('standard')
  const [showHelp, setShowHelp] = useState(false)
  const [ggufName, setGgufName] = useState('')
  const [ggufRepo, setGgufRepo] = useState('')
  const [ggufFile, setGgufFile] = useState('')
  const [ggufBase, setGgufBase] = useState('')
  // CivitAI
  const [civitaiUrl, setCivitaiUrl] = useState('')
  const [civitaiResolving, setCivitaiResolving] = useState(false)
  const [civitaiResult, setCivitaiResult] = useState(null)
  const [civitaiError, setCivitaiError] = useState('')
  // Ollama
  const [ollamaModel, setOllamaModel] = useState('')
  const timer = useRef(null)

  const refresh = () => {
    fetch('/api/images').then(r => r.json()).then(setImages).catch(() => {})
    fetch('/api/diffusion/status').then(r => r.json()).then(setDiffStatus).catch(() => {})
    fetch('/api/diffusion/models').then(r => r.json()).then(d => {
      setModels(d)
    }).catch(() => {})
  }

  useEffect(() => {
    refresh()
    timer.current = setInterval(refresh, 5000)
    return () => clearInterval(timer.current)
  }, [])

  const unload = () => {
    fetch('/api/diffusion/unload', { method: 'POST' }).then(refresh)
  }

  const addCustomModel = () => {
    const name = customModel.trim()
    if (!name || models.some(m => m.name === name)) return
    fetch('/api/diffusion/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name }),
    }).then(() => { setCustomModel(''); refresh() })
  }

  const loadModel = (name) => {
    if (loading) return
    setLoading(true)
    setGenMsg(`Loading pipeline: ${name}…`)
    fetch('/api/diffusion/load', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name }),
    })
      .then(r => r.json())
      .then(d => {
        setGenMsg(d.error ? `Error: ${d.error}` : d.status)
        setLoading(false)
        refresh()
      })
      .catch(e => { setGenMsg(`Error: ${e}`); setLoading(false) })
  }

  const addCustomGGUF = () => {
    if (!ggufName.trim() || !ggufRepo.trim() || !ggufFile.trim() || !ggufBase.trim()) return
    fetch('/api/diffusion/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({
        model: ggufName.trim(),
        source: 'huggingface',
        format: 'gguf',
        gguf_repo: ggufRepo.trim(),
        gguf_file: ggufFile.trim(),
        base_pipeline: ggufBase.trim(),
      }),
    }).then(() => {
      setGgufName(''); setGgufRepo(''); setGgufFile(''); setGgufBase('')
      refresh()
    })
  }

  const resolveCivitai = () => {
    if (!civitaiUrl.trim() || civitaiResolving) return
    setCivitaiResolving(true)
    setCivitaiError('')
    setCivitaiResult(null)
    fetch('/api/diffusion/resolve_civitai', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ url: civitaiUrl.trim() }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) setCivitaiError(d.error)
        else setCivitaiResult(d)
        setCivitaiResolving(false)
      })
      .catch(e => { setCivitaiError(String(e)); setCivitaiResolving(false) })
  }

  const addCivitaiModel = (version, file) => {
    const name = `${civitaiResult.name} (${version.name})`
    const isSDXL = version.pipeline_class === 'StableDiffusionXLPipeline'
    const recommended = {}
    if (isSDXL) recommended.clip_skip = 2
    fetch('/api/diffusion/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({
        model: name,
        source: 'civitai',
        download_url: version.download_url,
        civitai_filename: file.name,
        pipeline_class: version.pipeline_class,
        description: `CivitAI · ${version.base_model} · ${file.format}`,
        recommended: Object.keys(recommended).length ? recommended : undefined,
      }),
    }).then(() => {
      setCivitaiResult(null)
      setCivitaiUrl('')
      refresh()
    })
  }

  const addOllamaModel = () => {
    const name = ollamaModel.trim()
    if (!name || models.some(m => m.name === name)) return
    fetch('/api/diffusion/add_model', {
      method: 'POST', headers: CT,
      body: JSON.stringify({ model: name, source: 'ollama' }),
    }).then(() => { setOllamaModel(''); refresh() })
  }

  const applyRecommended = () => {
    if (diffStatus.recommended) {
      if (diffStatus.recommended.steps != null) setGenSteps(diffStatus.recommended.steps)
      if (diffStatus.recommended.guidance_scale != null) setGenGuidance(diffStatus.recommended.guidance_scale)
      if (diffStatus.recommended.clip_skip != null) setGenClipSkip(diffStatus.recommended.clip_skip)
    }
  }

  const generate = () => {
    if (!prompt.trim() || generating || !diffStatus.pipeline_loaded) return
    setGenerating(true)
    setGenMsg(`Generating${genBatch > 1 ? ` (${genBatch} images)` : ''}…`)
    fetch('/api/diffusion/generate', {
      method: 'POST', headers: CT,
      body: JSON.stringify({
        prompt: prompt.trim(),
        model: diffStatus.loaded_model,
        negative_prompt: negPrompt,
        width: genWidth,
        height: genHeight,
        steps: genSteps,
        guidance_scale: genGuidance,
        clip_skip: genClipSkip,
        seed: genSeed,
        batch_count: genBatch,
      }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) setGenMsg(`Error: ${d.error}`)
        else {
          const names = d.images.map(i => i.filename).join(', ')
          setGenMsg(`Done — ${d.count} image${d.count > 1 ? 's' : ''}: ${names}`)
        }
        setGenerating(false)
        refresh()
      })
      .catch(e => { setGenMsg(`Error: ${e}`); setGenerating(false) })
  }

  return (
    <div style={container}>
      {/* Pipeline status bar */}
      <div style={statusBar}>
        <span style={sectionLabel}>Diffusion Pipeline</span>
        {diffStatus.pipeline_loaded ? (
          <>
            <span style={loadedBadge}>● {diffStatus.loaded_model}</span>
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
            placeholder="Describe the image you want to generate…"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); generate() } }}
            disabled={generating}
            rows={2}
          />
          <button
            style={generating || !diffStatus.pipeline_loaded ? genBtnDisabled : genBtn}
            onClick={generate}
            disabled={generating || !diffStatus.pipeline_loaded}
          >
            {generating ? '⏳' : !diffStatus.pipeline_loaded ? '▶ No model' : '▶ Generate'}
          </button>
        </div>
        <div style={genOptionsRow}>
          <button style={advToggle} onClick={() => setShowAdvanced(!showAdvanced)}>
            {showAdvanced ? '▾ Less' : '▸ Options'}
          </button>
        </div>
        {showAdvanced && (
          <div style={advancedGrid}>
            <label style={advLabel}>Negative prompt</label>
            <input style={advInput} value={negPrompt} onChange={e => setNegPrompt(e.target.value)} placeholder="blur, low quality, watermark" />
            <label style={advLabel}>Width</label>
            <input style={advInput} type="number" value={genWidth} onChange={e => setGenWidth(+e.target.value)} step={64} min={256} max={2048} />
            <label style={advLabel}>Height</label>
            <input style={advInput} type="number" value={genHeight} onChange={e => setGenHeight(+e.target.value)} step={64} min={256} max={2048} />
            <label style={advLabel}>Steps</label>
            <input style={advInput} type="number" value={genSteps} onChange={e => setGenSteps(+e.target.value)} min={1} max={100} />
            <label style={advLabel}>Guidance</label>
            <input style={advInput} type="number" value={genGuidance} onChange={e => setGenGuidance(+e.target.value)} step={0.5} min={0} max={30} />
            <label style={advLabel}>Clip Skip</label>
            <input style={advInput} type="number" value={genClipSkip} onChange={e => setGenClipSkip(+e.target.value)} min={0} max={12} title="0 = off, 2 = common for SDXL finetunes" />
            <label style={advLabel}>Seed</label>
            <input style={advInput} type="number" value={genSeed} onChange={e => setGenSeed(+e.target.value)} min={-1} title="-1 = random" />
            <label style={advLabel}>Batch Count</label>
            <input style={advInput} type="number" value={genBatch} onChange={e => setGenBatch(Math.max(1, Math.min(50, +e.target.value)))} min={1} max={50} title="Number of images to generate" />
          </div>
        )}
        {genMsg && <div style={genMsgStyle}>{genMsg}</div>}
        {diffStatus.recommended && Object.keys(diffStatus.recommended).length > 0 && (
          <div style={recommendedHint}>
            Tip: recommended for this model: {[
              diffStatus.recommended.steps != null && `${diffStatus.recommended.steps} steps`,
              diffStatus.recommended.guidance_scale != null && `guidance ${diffStatus.recommended.guidance_scale}`,
              diffStatus.recommended.clip_skip != null && `clip skip ${diffStatus.recommended.clip_skip}`,
            ].filter(Boolean).join(', ')}
            <button style={applyBtn} onClick={applyRecommended}>Apply</button>
          </div>
        )}
        {diffStatus.recommended && diffStatus.recommended.prompt_hint && (
          <div style={promptHint}>
            ℹ Prompt template: <code style={{color:'#d2a8ff'}}>{diffStatus.recommended.prompt_hint}</code>
          </div>
        )}
      </div>

      {/* Model selector panel */}
      <div style={modelPanel}>
        <div style={modelPanelHeader}>
          <span style={sectionLabel}>Models</span>
          <button style={helpToggle} onClick={() => setShowHelp(!showHelp)}>{showHelp ? '\u2139 \u25be' : '\u2139 \u25b8'}</button>
        </div>
        {showHelp && (
          <div style={helpPanel}>
            <div style={helpRow}><strong>HuggingFace</strong> \u2014 Standard safetensors (<code>org/model-name</code>) or GGUF quantized files. Browse: <em>huggingface.co \u2192 Tasks \u2192 Text to Image</em></div>
            <div style={helpRow}><strong>CivitAI</strong> \u2014 Single-file checkpoints. Paste a model URL (e.g. <code>civitai.com/models/133005</code>) or model ID. Supports SD 1.5, SDXL, Flux, SD3 checkpoints. Set <code>CIVITAI_API_KEY</code> in .env for gated models.</div>
            <div style={helpRow}><strong>Ollama</strong> \u2014 Models from the Ollama registry. Currently experimental for image generation.</div>
            <div style={helpRow}>Supported GGUF types: Q4_0, Q4_1, Q5_0, Q5_1, Q8_0, Q2_K, Q3_K, Q4_K, Q5_K, Q6_K, BF16</div>
            <div style={helpRow}>Common GGUF bases: <code>black-forest-labs/FLUX.1-schnell</code> (fast, 4-step) \u00b7 <code>black-forest-labs/FLUX.1-dev</code> (quality, 20+ step)</div>
          </div>
        )}
        <div style={addModelSection}>
          {/* Source selector */}
          <div style={sourceToggle}>
            <button style={addSource === 'huggingface' ? srcActive : srcBtn} onClick={() => setAddSource('huggingface')}>HuggingFace</button>
            <button style={addSource === 'civitai' ? srcActive : srcBtn} onClick={() => setAddSource('civitai')}>CivitAI</button>
            <button style={addSource === 'ollama' ? srcActive : srcBtn} onClick={() => setAddSource('ollama')}>Ollama</button>
          </div>

          {addSource === 'huggingface' && (
            <>
              <div style={addModeToggle}>
                <button style={addMode === 'standard' ? addModeActive : addModeBtn} onClick={() => setAddMode('standard')}>Standard</button>
                <button style={addMode === 'gguf' ? addModeActive : addModeBtn} onClick={() => setAddMode('gguf')}>GGUF</button>
              </div>
              {addMode === 'standard' ? (
                <div style={addModelRow}>
                  <input
                    style={addModelInput}
                    value={customModel}
                    onChange={e => setCustomModel(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') addCustomModel() }}
                    placeholder="org/model-name"
                  />
                  <button style={addModelBtn} onClick={addCustomModel} disabled={!customModel.trim()}>+ Add</button>
                </div>
              ) : (
                <div style={ggufForm}>
                  <input style={ggufInput} value={ggufName} onChange={e => setGgufName(e.target.value)} placeholder="Display name (e.g. my-model-Q4)" />
                  <input style={ggufInput} value={ggufRepo} onChange={e => setGgufRepo(e.target.value)} placeholder="HuggingFace repo (e.g. city96/FLUX.1-dev-gguf)" />
                  <input style={ggufInput} value={ggufFile} onChange={e => setGgufFile(e.target.value)} placeholder="GGUF filename (e.g. flux1-dev-Q4_0.gguf)" />
                  <input style={ggufInput} value={ggufBase} onChange={e => setGgufBase(e.target.value)} placeholder="Base pipeline (e.g. black-forest-labs/FLUX.1-dev)" />
                  <button style={addModelBtn} onClick={addCustomGGUF} disabled={!ggufName.trim() || !ggufRepo.trim() || !ggufFile.trim() || !ggufBase.trim()}>+ Add GGUF</button>
                </div>
              )}
            </>
          )}

          {addSource === 'civitai' && (
            <div style={civitaiSection}>
              <div style={addModelRow}>
                <input
                  style={addModelInput}
                  value={civitaiUrl}
                  onChange={e => setCivitaiUrl(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') resolveCivitai() }}
                  placeholder="CivitAI URL or model ID (e.g. civitai.com/models/133005 or 133005)"
                />
                <button style={addModelBtn} onClick={resolveCivitai} disabled={!civitaiUrl.trim() || civitaiResolving}>
                  {civitaiResolving ? '\u2026' : '\u2192 Resolve'}
                </button>
              </div>
              {civitaiError && <div style={errMsg}>{civitaiError}</div>}
              {civitaiResult && (
                <div style={civitaiResultBox}>
                  <div style={civitaiTitle}>{civitaiResult.name} <span style={civitaiType}>{civitaiResult.type}</span></div>
                  {civitaiResult.versions.map(v => (
                    <div key={v.id} style={civitaiVersion}>
                      <span style={civitaiVerName}>{v.name}</span>
                      <span style={civitaiBase}>{v.base_model}</span>
                      {v.files.map(f => (
                        <button
                          key={f.name}
                          style={civitaiFileBtn}
                          onClick={() => addCivitaiModel(v, f)}
                          title={f.name}
                        >
                          + {f.name.length > 30 ? f.name.slice(0, 27) + '\u2026' : f.name}
                          {f.size_kb ? ` (${(f.size_kb / 1024 / 1024).toFixed(1)} GB)` : ''}
                          {f.fp ? ` ${f.fp}` : ''}
                        </button>
                      ))}
                    </div>
                  ))}
                  {civitaiResult.versions.length === 0 && <div style={errMsg}>No downloadable SafeTensor files found.</div>}
                </div>
              )}
            </div>
          )}

          {addSource === 'ollama' && (
            <div>
              <div style={addModelRow}>
                <input
                  style={addModelInput}
                  value={ollamaModel}
                  onChange={e => setOllamaModel(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') addOllamaModel() }}
                  placeholder="Ollama model name (e.g. model:tag)"
                />
                <button style={addModelBtn} onClick={addOllamaModel} disabled={!ollamaModel.trim()}>+ Add</button>
              </div>
              <div style={ollamaNote}>Ollama-sourced image generation models are experimental. Model must be compatible with the diffusion pipeline to load successfully.</div>
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
              <div style={mlBadges}>                {m.source && m.source !== 'huggingface' && <span style={m.source === 'civitai' ? civitaiBadge : ollamaBadge}>{m.source}</span>}                <span style={m.format === 'gguf' ? ggufFmtBadge : stFmtBadge}>{m.format || 'safetensors'}</span>                {m.downloaded
                  ? <span style={dlBadge}>downloaded</span>
                  : m.downloading
                    ? <span style={dlProgressBadge}>downloading…</span>
                    : <span style={notDlBadge}>not downloaded</span>}
                {m.loaded && <span style={loadedModelBadge}>● loaded</span>}
              </div>
              <div style={mlActions}>
                {!m.downloaded && !m.loaded && (
                  <button
                    style={downloadBtn}
                    onClick={() => loadModel(m.name)}
                    disabled={loading}
                  >
                    {loading ? '…' : '⬇ Download'}
                  </button>
                )}
                {m.downloaded && !m.loaded && (
                  <button
                    style={swapBtn}
                    onClick={() => loadModel(m.name)}
                    disabled={loading}
                  >
                    {loading ? '…' : '⇄ Swap to'}
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

      {/* Gallery grid */}
      <div style={sectionLabel}>
        Generated Images ({images.length})
      </div>

      {images.length === 0 ? (
        <div style={emptyMsg}>
          No images yet. Type a prompt above or let agents use the <code>generate_image</code> tool.
        </div>
      ) : (
        <div style={grid}>
          {images.map(img => (
            <div
              key={img.filename}
              style={card}
              onClick={() => setSelected(img)}
            >
              <img
                src={img.url}
                alt={img.filename}
                style={thumb}
                loading="lazy"
              />
              <div style={cardFooter}>
                <span style={cardName}>{img.meta?.prompt ? img.meta.prompt.slice(0, 60) + (img.meta.prompt.length > 60 ? '…' : '') : img.filename}</span>
                <span style={cardSize}>{fmtSize(img.size)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {selected && (
        <div style={lightbox} onClick={() => setSelected(null)}>
          <div style={lightboxLayout} onClick={e => e.stopPropagation()}>
            <img src={selected.url} alt={selected.filename} style={lightboxImg} />
            <div style={metaPanel}>
              <div style={metaHeader}>{selected.filename}</div>
              <div style={metaSize}>{fmtSize(selected.size)}</div>
              {selected.meta ? (
                <>
                  <div style={metaLabel}>Prompt</div>
                  <div style={metaValue}>{selected.meta.prompt}</div>
                  {selected.meta.negative_prompt && (
                    <><div style={metaLabel}>Negative</div><div style={metaValue}>{selected.meta.negative_prompt}</div></>
                  )}
                  <div style={metaGrid}>
                    <span style={metaLabel}>Model</span><span style={metaVal}>{selected.meta.model}</span>
                    <span style={metaLabel}>Size</span><span style={metaVal}>{selected.meta.width}×{selected.meta.height}</span>
                    <span style={metaLabel}>Steps</span><span style={metaVal}>{selected.meta.steps}</span>
                    <span style={metaLabel}>Guidance</span><span style={metaVal}>{selected.meta.guidance_scale}</span>
                    {selected.meta.clip_skip > 0 && (
                      <><span style={metaLabel}>Clip Skip</span><span style={metaVal}>{selected.meta.clip_skip}</span></>
                    )}
                    {selected.meta.seed != null && (
                      <><span style={metaLabel}>Seed</span><span style={metaVal}>{selected.meta.seed}</span></>
                    )}
                    <span style={metaLabel}>Pipeline</span><span style={metaVal}>{selected.meta.pipeline_type}</span>
                  </div>
                </>
              ) : (
                <div style={metaVal}>No metadata available</div>
              )}
              <button style={lightboxCloseBtn} onClick={() => setSelected(null)}>✕ Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const fmtSize = (bytes) => {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

const container = { padding: '12px 16px', overflowY: 'auto', height: '100%' }

const statusBar = {
  display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
  padding: '8px 14px', background: '#161b22', border: '1px solid #30363d',
  borderRadius: 8,
}

const sectionLabel = {
  fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase',
  color: '#8b949e', marginBottom: 8,
}

const loadedBadge = { color: '#3fb950', fontSize: 11, fontWeight: 600 }
const idleBadge = { color: '#484f58', fontSize: 11 }

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

// Help & add-model section
const helpToggle = {
  fontSize: 12, background: 'transparent', border: 'none', color: '#58a6ff',
  cursor: 'pointer', padding: '2px 6px',
}

const helpPanel = {
  background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
  padding: '8px 12px', marginBottom: 10, fontSize: 10, color: '#8b949e', lineHeight: 1.6,
}

const helpRow = { marginBottom: 4 }

const addModelSection = { marginBottom: 8 }

const sourceToggle = { display: 'flex', gap: 2, marginBottom: 8 }

const srcBtn = {
  fontSize: 10, padding: '4px 12px', background: '#21262d', color: '#8b949e',
  border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer',
}

const srcActive = {
  ...srcBtn, color: '#58a6ff', border: '1px solid #58a6ff60', background: '#58a6ff12',
}

const addModeToggle = { display: 'flex', gap: 2, marginBottom: 6 }

const addModeBtn = {
  fontSize: 9, padding: '3px 10px', background: '#21262d', color: '#8b949e',
  border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer',
}

const addModeActive = {
  ...addModeBtn, color: '#58a6ff', border: '1px solid #58a6ff60',
}

const ggufForm = { display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 480 }

const ggufInput = {
  background: '#0d1117', border: '1px solid #30363d', borderRadius: 4,
  padding: '4px 8px', color: '#c9d1d9', fontSize: 11, fontFamily: 'inherit',
}

const stFmtBadge = {
  fontSize: 7, fontWeight: 700, color: '#8b949e', background: '#8b949e18',
  borderRadius: 3, padding: '1px 5px', textTransform: 'uppercase',
}

const ggufFmtBadge = {
  fontSize: 7, fontWeight: 700, color: '#d2a8ff', background: '#d2a8ff18',
  borderRadius: 3, padding: '1px 5px', textTransform: 'uppercase',
}

const recommendedHint = {
  display: 'flex', alignItems: 'center', gap: 8, fontSize: 10,
  color: '#d29922', marginTop: 8, padding: '4px 8px',
  background: '#d2992210', borderRadius: 4,
}

const applyBtn = {
  fontSize: 9, padding: '2px 8px', background: '#21262d', color: '#d29922',
  border: '1px solid #d2992240', borderRadius: 3, cursor: 'pointer',
}

const promptHint = {
  display: 'flex', alignItems: 'center', gap: 8, fontSize: 10,
  color: '#8b949e', marginTop: 4, padding: '4px 8px',
  background: '#0d1117', borderRadius: 4, lineHeight: 1.5,
  flexWrap: 'wrap',
}

// CivitAI resolve styles
const civitaiSection = { display: 'flex', flexDirection: 'column', gap: 6 }
const errMsg = { fontSize: 10, color: '#f85149', marginTop: 4 }
const civitaiResultBox = {
  background: '#0d1117', border: '1px solid #30363d', borderRadius: 6,
  padding: '8px 12px', marginTop: 4,
}
const civitaiTitle = { fontSize: 12, color: '#c9d1d9', fontWeight: 600, marginBottom: 6 }
const civitaiType = { fontSize: 9, color: '#8b949e', fontWeight: 400, marginLeft: 6 }
const civitaiVersion = {
  display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6,
  marginBottom: 4, paddingLeft: 4,
}
const civitaiVerName = { fontSize: 10, color: '#c9d1d9', fontWeight: 600, minWidth: 80 }
const civitaiBase = { fontSize: 9, color: '#8b949e', minWidth: 60 }
const civitaiFileBtn = {
  fontSize: 9, padding: '2px 8px', background: '#238636', color: '#fff',
  border: 'none', borderRadius: 3, cursor: 'pointer', whiteSpace: 'nowrap',
}

// Ollama note
const ollamaNote = {
  fontSize: 10, color: '#8b949e', marginTop: 4, fontStyle: 'italic',
}

// Source badges for model rows
const civitaiBadge = {
  fontSize: 7, fontWeight: 700, color: '#1f6feb', background: '#1f6feb18',
  borderRadius: 3, padding: '1px 5px', textTransform: 'uppercase',
}

const ollamaBadge = {
  fontSize: 7, fontWeight: 700, color: '#3fb950', background: '#3fb95018',
  borderRadius: 3, padding: '1px 5px', textTransform: 'uppercase',
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

const dlProgressBadge = {
  fontSize: 8, fontWeight: 700, color: '#d29922', background: '#d2992218',
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

const grid = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: 12,
}

const card = {
  background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  overflow: 'hidden', cursor: 'pointer', transition: 'border-color 0.2s',
}

const thumb = {
  width: '100%', height: 200, objectFit: 'cover', display: 'block',
}

const cardFooter = {
  padding: '6px 10px', display: 'flex', justifyContent: 'space-between',
  alignItems: 'center',
}

const cardName = { fontSize: 10, color: '#8b949e', fontFamily: 'monospace' }
const cardSize = { fontSize: 10, color: '#484f58' }

const emptyMsg = {
  padding: 40, textAlign: 'center', color: '#484f58', fontSize: 12, lineHeight: 1.6,
}

const lightbox = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 1000, cursor: 'pointer',
}

const lightboxLayout = {
  display: 'flex', gap: 16, maxWidth: '95vw', maxHeight: '92vh',
  cursor: 'default',
}

const lightboxImg = {
  maxWidth: '60vw', maxHeight: '90vh', objectFit: 'contain', borderRadius: 8, flexShrink: 0,
}

const metaPanel = {
  width: 300, background: '#161b22', border: '1px solid #30363d', borderRadius: 8,
  padding: '14px 16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6,
}

const metaHeader = {
  fontSize: 11, color: '#c9d1d9', fontFamily: 'monospace', fontWeight: 600,
  wordBreak: 'break-all',
}

const metaSize = { fontSize: 10, color: '#484f58', marginBottom: 6 }

const metaLabel = {
  fontSize: 9, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase',
  color: '#8b949e', marginTop: 4,
}

const metaValue = {
  fontSize: 11, color: '#c9d1d9', lineHeight: 1.5, wordBreak: 'break-word',
}

const metaGrid = {
  display: 'grid', gridTemplateColumns: '80px 1fr', gap: '2px 8px',
  fontSize: 10, marginTop: 6,
}

const metaVal = { fontSize: 10, color: '#c9d1d9', fontFamily: 'monospace' }

const lightboxCloseBtn = {
  marginTop: 'auto', fontSize: 10, padding: '6px 12px', alignSelf: 'flex-end',
  background: '#21262d', color: '#f85149', border: '1px solid #f8514930',
  borderRadius: 4, cursor: 'pointer',
}

// Generate form styles
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

const genBtnDisabled = {
  ...genBtn, background: '#21262d', color: '#484f58', cursor: 'wait',
}

const genOptionsRow = {
  display: 'flex', gap: 8, alignItems: 'center', marginTop: 8,
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

const genMsgStyle = {
  fontSize: 10, color: '#8b949e', marginTop: 8,
}
