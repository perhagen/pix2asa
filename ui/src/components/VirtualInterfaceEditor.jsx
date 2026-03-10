/**
 * Editor for virtual (context-mode) interface mappings.
 *
 * Each row maps a PIX source interface to:
 *   - physical: the system-level sub-interface (e.g. Port-channel1.1400)
 *   - nameif:   the logical name used in both allocate-interface and as the
 *               context interface name (e.g. outside)
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

export default function VirtualInterfaceEditor({ config, rows, onChange }) {
  const srcIfs = parseSrcInterfaces(config)

  // Nameifs already used by other rows (for duplicate detection)
  const usedNameifs = rows.reduce((acc, r) => {
    if (r.nameif) acc.add(r.nameif.toLowerCase())
    return acc
  }, new Set())

  function addRow() {
    onChange([...rows, { src_pix_if: '', physical: '', nameif: '' }])
  }

  function removeRow(idx) {
    onChange(rows.filter((_, i) => i !== idx))
  }

  function updateRow(idx, field, value) {
    const next = rows.map((r, i) => i === idx ? { ...r, [field]: value } : r)
    onChange(next)
  }

  return (
    <div className="mt-3">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
            <th className="py-1 pr-3">Source PIX interface</th>
            <th className="py-1 pr-3">System physical interface</th>
            <th className="py-1 pr-3">Logical name (nameif)</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const dupeNameif =
              row.nameif &&
              rows.some((r, i) => i !== idx && r.nameif.toLowerCase() === row.nameif.toLowerCase())
            return (
              <tr key={idx} className="border-b border-gray-100">
                <td className="py-1 pr-3">
                  <select
                    className="form-input text-xs"
                    value={row.src_pix_if}
                    onChange={(e) => updateRow(idx, 'src_pix_if', e.target.value)}
                  >
                    <option value="">— select —</option>
                    {srcIfs.map((iface) => (
                      <option key={iface} value={iface}>{iface}</option>
                    ))}
                  </select>
                </td>
                <td className="py-1 pr-3">
                  <input
                    className="form-input text-xs font-mono"
                    type="text"
                    placeholder="Port-channel1.1400"
                    value={row.physical}
                    onChange={(e) => updateRow(idx, 'physical', e.target.value)}
                  />
                </td>
                <td className="py-1 pr-3">
                  <input
                    className={`form-input text-xs font-mono ${dupeNameif ? 'border-red-400' : ''}`}
                    type="text"
                    placeholder="outside"
                    value={row.nameif}
                    onChange={(e) => updateRow(idx, 'nameif', e.target.value)}
                  />
                  {dupeNameif && (
                    <p className="text-xs text-red-600 mt-0.5">Duplicate nameif</p>
                  )}
                </td>
                <td className="py-1">
                  <button
                    className="text-xs text-red-500 hover:text-red-700 px-1"
                    onClick={() => removeRow(idx)}
                    title="Remove"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <button className="btn btn-secondary text-xs mt-2" onClick={addRow}>
        + Add interface
      </button>
    </div>
  )
}
