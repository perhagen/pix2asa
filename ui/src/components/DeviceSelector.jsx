export default function DeviceSelector({ devices, value, onChange }) {
  if (!devices) {
    return (
      <div className="panel">
        <div className="panel-title">Step 2 — Target Device Type</div>
        <p className="text-sm text-gray-500">Loading device list…</p>
      </div>
    )
  }

  const targets = devices.filter((d) => d.device_type === 'target')

  return (
    <div className="panel">
      <div className="panel-title">Step 2 — Target Device Type</div>
      <div className="flex items-center gap-3">
        <label className="form-label whitespace-nowrap">
          Target device type:
        </label>
        <select
          className="form-input max-w-xs"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
        >
          <option value="">— select —</option>
          {targets.map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
