import { useRef } from 'react'

export default function ConfigInput({ value, onChange, onFilename }) {
  const fileRef = useRef(null)

  const lines = value ? value.split('\n').length : 0
  const chars = value ? value.length : 0

  function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => {
      onChange(ev.target.result)
      onFilename?.(file.name)
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  return (
    <div className="panel">
      <div className="panel-title">Step 1 — Source Configuration</div>

      <div className="flex gap-2 mb-2">
        <button
          className="btn btn-secondary"
          onClick={() => fileRef.current?.click()}
        >
          Load file…
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => { onChange(''); onFilename?.('') }}
          disabled={!value}
        >
          Clear
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.cfg,.conf"
          className="hidden"
          onChange={handleFile}
        />
        {value && (
          <span className="text-xs text-gray-500 self-center ml-2">
            {lines} lines · {chars} chars
          </span>
        )}
      </div>

      <textarea
        className="config-area"
        rows={16}
        placeholder="Paste PIX configuration here or use Load file…"
        value={value}
        onChange={(e) => { onChange(e.target.value); onFilename?.('') }}
        spellCheck={false}
      />
    </div>
  )
}
