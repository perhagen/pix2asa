import { useEffect, useRef } from 'react'

const TITLES = {
  source: 'Source Configuration (PIX)',
  target: 'Target Configuration (ASA)',
  log: 'Conversion Log',
}

export default function ConfigViewer({ mode, content, onClose }) {
  const textRef = useRef(null)

  // Focus textarea on open
  useEffect(() => {
    textRef.current?.focus()
  }, [mode])

  // Close on Escape
  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  function copyToClipboard() {
    navigator.clipboard?.writeText(content ?? '')
  }

  function downloadFile() {
    const ext = mode === 'log' ? 'txt' : 'cfg'
    const blob = new Blob([content ?? ''], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pix2asa-${mode}.${ext}`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded border border-gray-300 shadow-xl flex flex-col w-[90vw] max-w-5xl h-[80vh]">
        {/* Title bar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-gray-50 rounded-t">
          <h3 className="text-sm font-semibold">{TITLES[mode] ?? mode}</h3>
          <div className="flex gap-2">
            <button className="btn btn-secondary text-xs" onClick={copyToClipboard}>
              Copy
            </button>
            <button className="btn btn-secondary text-xs" onClick={downloadFile}>
              Download
            </button>
            <button className="btn btn-secondary text-xs" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {/* Content */}
        <textarea
          ref={textRef}
          className="flex-1 p-3 font-mono text-xs resize-none outline-none rounded-b overflow-auto"
          readOnly
          value={content ?? ''}
          cols={80}
        />
      </div>
    </div>
  )
}
