import React from 'react'

/**
 * Parse physical interface names referenced in PIX config text.
 * Returns sorted unique list (e.g. ["ethernet0", "ethernet1", "gigabitethernet0"]).
 */
function parseSrcInterfaces(config) {
  if (!config) return []
  const seen = new Set()
  for (const m of config.matchAll(
    /^(?:interface|nameif)\s+([eEgG][a-zA-Z0-9/]+)/gm
  )) {
    seen.add(m[1].toLowerCase())
  }
  return [...seen].sort()
}

/**
 * Parse nameif mappings: physical → logical name.
 * e.g. { "ethernet0": "outside", "ethernet1": "inside" }
 */
function parseNameifs(config) {
  const map = {}
  if (!config) return map
  for (const m of config.matchAll(
    /^nameif\s+(\S+)\s+(\S+)\s+security\d+/gim
  )) {
    map[m[1].toLowerCase()] = m[2]
  }
  return map
}

/**
 * Parse trailing digits from a physical interface name.
 * e.g. "Port-channel1.1400" → { base: "Port-channel1.", start: 1400 }
 * Returns null if no trailing digits found.
 */
function parseBasePhysical(s) {
  const m = s.match(/^(.*?)(\d+)$/)
  if (!m) return null
  return { base: m[1], start: parseInt(m[2], 10) }
}

export default function InterfaceMapper({
  config,
  device,
  interfaceMap,
  onChange,
  contextMode,
  onContextModeChange,
  virtualInterfaces,
  onVirtualInterfacesChange,
}) {
  const srcIfs = parseSrcInterfaces(config)
  const nameifs = parseNameifs(config)
  const dstIfs = device?.interfaces ?? []

  // Local state for the auto-increment base physical interface input
  const [basePhysical, setBasePhysical] = React.useState('')
  // Shared pool of physical interface suggestions shown in every row's dropdown
  const [physicalPool, setPhysicalPool] = React.useState([])

  // Seed pool from device interfaces when a device is selected in context mode
  React.useEffect(() => {
    if (contextMode && device?.interfaces?.length) {
      setPhysicalPool(device.interfaces)
    }
  }, [contextMode, device])

  if (!config) return null

  // ---------------------------------------------------------------------------
  // Normal mode helpers
  // ---------------------------------------------------------------------------

  function setMapping(src, dst) {
    onChange({ ...interfaceMap, [src]: dst || undefined })
  }

  // Build a set of destination interfaces already claimed by other source rows
  const usedDst = new Set(Object.values(interfaceMap).filter(Boolean))

  // ---------------------------------------------------------------------------
  // Context mode helpers
  // ---------------------------------------------------------------------------

  // Build lookup: src_pix_if → { physical, nameif }
  const ctxMap = Object.fromEntries(
    virtualInterfaces.map((vi) => [vi.src_pix_if, { physical: vi.physical, nameif: vi.nameif }])
  )

  /** Apply a new base physical interface: auto-fill all rows and rebuild the shared pool */
  function applyBasePhysical(value) {
    setBasePhysical(value)
    const parsed = parseBasePhysical(value.trim())
    if (!parsed) return
    const computed = srcIfs.map((_, i) => `${parsed.base}${parsed.start + i}`)
    // Rebuild pool: auto-computed values + any manually added values not in the new set
    const autoSet = new Set(computed)
    setPhysicalPool([...computed, ...physicalPool.filter((v) => !autoSet.has(v))])
    const newVifs = srcIfs.map((s, i) => ({
      src_pix_if: s,
      physical: computed[i],
      nameif: nameifs[s] || ctxMap[s]?.nameif || s,
    }))
    onVirtualInterfacesChange(newVifs)
  }

  function setCtxField(src, field, value) {
    const row = ctxMap[src] || { physical: '', nameif: '' }
    const updated = { ...row, [field]: value }
    // If a new physical value is typed that isn't in the pool, add it
    if (field === 'physical' && value && !physicalPool.includes(value)) {
      setPhysicalPool((prev) => [...prev, value])
    }
    const newVifs = srcIfs
      .map((s) => {
        const r = s === src ? updated : (ctxMap[s] || null)
        if (!r || (!r.physical && !r.nameif)) return null
        return { src_pix_if: s, physical: r.physical || '', nameif: r.nameif || '' }
      })
      .filter(Boolean)
    onVirtualInterfacesChange(newVifs)
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="panel">
      <div className="panel-title">Step 3 — Interface Mapping</div>

      {/* Context mode toggle */}
      <div className="mb-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={contextMode}
            onChange={(e) => onContextModeChange(e.target.checked)}
          />
          <span>
            Context mode — map to virtual (logical) interfaces and generate{' '}
            <code className="text-xs bg-gray-100 px-1 rounded">:::: system-config ::::</code> block
          </span>
        </label>
      </div>

      {srcIfs.length === 0 ? (
        <p className="text-sm text-gray-500">No interfaces found in source config.</p>
      ) : contextMode ? (
        // -------------------------------------------------------------------
        // Context mode: system physical + nameif text inputs
        // -------------------------------------------------------------------
        <div>
          <div className="mb-3 flex items-center gap-3">
            <label className="text-xs text-gray-600 whitespace-nowrap">Starting physical interface:</label>
            <input
              className="form-input text-xs font-mono w-64"
              type="text"
              placeholder="Port-channel1.1400"
              value={basePhysical}
              onChange={(e) => applyBasePhysical(e.target.value)}
            />
            <span className="text-xs text-gray-400">auto-increments for each source interface</span>
          </div>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
              <th className="py-1 pr-4">Source Interface</th>
              <th className="py-1 pr-3">System Physical Interface</th>
              <th className="py-1 pr-3">Maps To (nameif)</th>
              <th className="py-1">Status</th>
            </tr>
          </thead>
          <tbody>
            {(() => {
              // Build set of physical values claimed by all rows
              const usedPhysicals = new Set(
                Object.values(ctxMap).map((r) => r.physical).filter(Boolean)
              )
              return srcIfs.map((src) => {
                const hint = nameifs[src]
                const row = ctxMap[src] || { physical: '', nameif: '' }
                const mapped = !!(row.physical && row.nameif)
                // Each row sees pool values not used by other rows, plus its own current value
                const availablePool = physicalPool.filter(
                  (v) => v === row.physical || !usedPhysicals.has(v)
                )
                const listId = `ctx-phys-${src}`
                return (
                  <tr key={src} className="border-b border-gray-100">
                    <td className="py-1 pr-4 text-right font-mono text-xs text-gray-700">
                      {src}
                      {hint && <span className="ml-1 text-gray-400">({hint})</span>}
                    </td>
                    <td className="py-1 pr-3">
                      <datalist id={listId}>
                        {availablePool.map((v) => <option key={v} value={v} />)}
                      </datalist>
                      <input
                        className="form-input text-xs font-mono w-full"
                        type="text"
                        list={listId}
                        placeholder="Port-channel1.1400"
                        value={row.physical}
                        onChange={(e) => setCtxField(src, 'physical', e.target.value)}
                      />
                    </td>
                    <td className="py-1 pr-3">
                      <input
                        className="form-input text-xs font-mono w-full"
                        type="text"
                        placeholder={hint || 'outside'}
                        value={row.nameif}
                        onChange={(e) => setCtxField(src, 'nameif', e.target.value)}
                      />
                    </td>
                    <td className="py-1 text-xs">
                      {mapped ? (
                        <span className="text-green-600">✓ mapped</span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                  </tr>
                )
              })
            })()}
          </tbody>
        </table>
        </div>
      ) : !device ? (
        <p className="text-sm text-gray-400 italic">Select a target device above to map interfaces, or enable context mode.</p>
      ) : (
        // -------------------------------------------------------------------
        // Normal mode: hardware interface dropdown
        // -------------------------------------------------------------------
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
              <th className="py-1 pr-4">Source Interface</th>
              <th className="py-1 pr-4">Maps To</th>
              <th className="py-1">Status</th>
            </tr>
          </thead>
          <tbody>
            {srcIfs.map((src) => {
              const logical = nameifs[src]
              const dst = interfaceMap[src] ?? ''
              const mapped = !!dst
              const availableDst = dstIfs.filter(
                (di) => di === dst || !usedDst.has(di)
              )
              return (
                <tr key={src} className="border-b border-gray-100">
                  <td className="py-1 pr-4 text-right font-mono text-xs text-gray-700">
                    {src}
                    {logical && (
                      <span className="ml-1 text-gray-400">({logical})</span>
                    )}
                  </td>
                  <td className="py-1 pr-4">
                    <select
                      className="form-input text-xs"
                      value={dst}
                      onChange={(e) => setMapping(src, e.target.value)}
                    >
                      <option value="">— auto —</option>
                      {availableDst.map((di) => (
                        <option key={di} value={di}>{di}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-1 text-xs">
                    {mapped ? (
                      <span className="text-green-600">✓ mapped</span>
                    ) : (
                      <span className="text-gray-400">auto</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
