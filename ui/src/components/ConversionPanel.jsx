import VirtualInterfaceEditor from './VirtualInterfaceEditor.jsx'

export default function ConversionPanel({
  disabled,
  loading,
  bootSystem,
  onBootSystemChange,
  sourceVersion,
  onSourceVersionChange,
  versionAutoDetected,
  targetVersion,
  onTargetVersionChange,
  custom5505,
  onCustom5505Change,
  convertNames,
  onConvertNamesChange,
  debug,
  onDebugChange,
  result,
  onConvert,
  onView,
}) {
  return (
    <div className="panel">
      <div className="panel-title">Step 4 — Conversion Options &amp; Actions</div>

      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 items-center max-w-lg mb-4">
        <label className="form-label">Source PIX version:</label>
        <div className="flex items-center gap-2">
          <select
            className="form-input max-w-xs"
            value={sourceVersion}
            onChange={(e) => onSourceVersionChange(Number(e.target.value))}
          >
            <option value={6}>PIX 6</option>
            <option value={7}>PIX 7</option>
          </select>
          {versionAutoDetected && (
            <span className="text-xs text-green-700 bg-green-100 border border-green-300 rounded px-2 py-0.5">
              auto-detected
            </span>
          )}
        </div>

        <label className="form-label">Target ASA version:</label>
        <select
          className="form-input max-w-xs"
          value={targetVersion}
          onChange={(e) => onTargetVersionChange(Number(e.target.value))}
        >
          <option value={84}>ASA 8.4+</option>
        </select>

        <label className="form-label">Boot image path:</label>
        <div>
          <input
            className="form-input max-w-xs"
            type="text"
            placeholder="flash:/asa.bin (optional)"
            value={bootSystem}
            onChange={(e) => onBootSystemChange(e.target.value)}
          />
          <p className="text-xs text-gray-400 mt-0.5">
            Must include flash:/, disk0:/, disk1:/, or tftp:// prefix
          </p>
        </div>

        <label className="form-label">ASA 5505:</label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={custom5505}
            onChange={(e) => onCustom5505Change(e.target.checked)}
          />
          Generate 5505-style switch port config
        </label>

        <label className="form-label">Name commands:</label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={convertNames}
            onChange={(e) => onConvertNamesChange(e.target.checked)}
          />
          Convert <code className="text-xs bg-gray-100 px-1 rounded">name</code> commands to host objects
        </label>

        <label className="form-label">Debug:</label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={debug}
            onChange={(e) => onDebugChange(e.target.checked)}
          />
          Log NAT translation table to conversion log
        </label>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <button
          className="btn btn-primary"
          disabled={disabled || loading}
          onClick={onConvert}
        >
          {loading ? 'Converting…' : 'Make target configuration'}
        </button>

        {result && (
          <>
            <button
              className="btn btn-secondary"
              onClick={() => onView('source')}
            >
              View source config
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => onView('target')}
            >
              View target config
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => onView('log')}
            >
              View log
            </button>
          </>
        )}
      </div>

      {result?.errors?.length > 0 && (
        <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
          <strong>Errors:</strong>
          <ul className="list-disc pl-4 mt-1">
            {result.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {result?.warnings?.length > 0 && (
        <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700">
          <strong>Warnings:</strong>
          <ul className="list-disc pl-4 mt-1">
            {result.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
