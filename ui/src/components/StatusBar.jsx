export default function StatusBar({ config }) {
  if (!config) {
    return (
      <div className="panel bg-yellow-50 border-yellow-300">
        <div className="panel-title">Status</div>
        <p className="text-sm text-yellow-700">
          No source configuration loaded. Paste or load a PIX config above.
        </p>
      </div>
    )
  }

  const lines = config.split('\n').length
  const hasHostname = /^hostname\s+\S/m.test(config)
  const version = config.match(/^PIX\s+Version\s+(\S+)/m)?.[1]
    ?? config.match(/^Cisco\s+PIX\s+Firewall\s+Version\s+(\S+)/m)?.[1]
    ?? null

  return (
    <div className="panel bg-green-50 border-green-300">
      <div className="panel-title">Status</div>
      <p className="text-sm text-green-800">
        Source configuration loaded: <strong>{lines}</strong> lines
        {version && (
          <span> · PIX version <strong>{version}</strong> (auto-detected)</span>
        )}
        {hasHostname && (
          <span>
            {' '}
            · hostname{' '}
            <strong>{config.match(/^hostname\s+(\S+)/m)?.[1]}</strong>
          </span>
        )}
      </p>
    </div>
  )
}
