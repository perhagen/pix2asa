import { useState, useEffect, useCallback } from 'react'
import { getDevices, getVersion, convertConfig } from './api.js'
import Header from './components/Header.jsx'
import ConfigInput from './components/ConfigInput.jsx'
import StatusBar from './components/StatusBar.jsx'
import DeviceSelector from './components/DeviceSelector.jsx'
import InterfaceMapper from './components/InterfaceMapper.jsx'
import ConversionPanel from './components/ConversionPanel.jsx'
import ConfigViewer from './components/ConfigViewer.jsx'

export default function App() {
  // --- API state ---
  const [devices, setDevices] = useState(null)
  const [version, setVersion] = useState(null)
  const [apiError, setApiError] = useState(null)

  // --- Wizard state ---
  const [sourceConfig, setSourceConfig] = useState('')
  const [sourceFilename, setSourceFilename] = useState('')
  const [targetPlatform, setTargetPlatform] = useState(null)
  const [interfaceMap, setInterfaceMap] = useState({})
  const [sourceVersion, setSourceVersion] = useState(6)
  const [versionAutoDetected, setVersionAutoDetected] = useState(false)
  const [targetVersion, setTargetVersion] = useState(84)
  const [bootSystem, setBootSystem] = useState('')
  const [custom5505, setCustom5505] = useState(false)
  const [convertNames, setConvertNames] = useState(true)
  const [debug, setDebug] = useState(true)
  const [contextMode, setContextMode] = useState(false)
  const [virtualInterfaces, setVirtualInterfaces] = useState([])

  // --- Conversion state ---
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [convError, setConvError] = useState(null)

  // --- Viewer state ---
  const [viewerMode, setViewerMode] = useState(null) // 'source' | 'target' | 'log'

  // Load devices + version on mount
  useEffect(() => {
    Promise.all([getDevices(), getVersion()])
      .then(([devs, ver]) => {
        setDevices(devs)
        setVersion(ver.version)
      })
      .catch((err) => setApiError(err.message))
  }, [])

  // Auto-detect PIX version from config header whenever source config changes
  useEffect(() => {
    const m = sourceConfig.match(/^PIX\s+Version\s+(\d+)\./m)
    if (m) {
      const major = parseInt(m[1], 10)
      setSourceVersion(major >= 7 ? 7 : 6)
      setVersionAutoDetected(true)
    } else {
      setVersionAutoDetected(false)
    }
  }, [sourceConfig])

  const selectedDevice = devices?.find((d) => d.slug === targetPlatform) ?? null

  // Can convert: need source config + (a target platform OR context mode with at least one mapping)
  const canConvert = !!sourceConfig && (
    !!targetPlatform ||
    (contextMode && virtualInterfaces.some((vi) => vi.src_pix_if && vi.physical && vi.nameif))
  )

  const handleConvert = useCallback(async () => {
    setLoading(true)
    setConvError(null)
    try {
      // In context mode, virtual_interfaces handles all mappings; interface_map is not used.
      // In normal mode, build interface_map from explicit overrides only.
      const explicitMap = contextMode ? {} : Object.fromEntries(
        Object.entries(interfaceMap).filter(([, v]) => v)
      )
      const res = await convertConfig({
        config: sourceConfig,
        target_platform: targetPlatform,
        source_version: sourceVersion,
        target_version: targetVersion,
        interface_map: explicitMap,
        custom_5505: custom5505,
        boot_system: bootSystem || null,
        convert_names: convertNames,
        debug,
        source_filename: sourceFilename || '',
        context_mode: contextMode,
        virtual_interfaces: virtualInterfaces.filter(
          (vi) => vi.src_pix_if && vi.physical && vi.nameif
        ),
      })
      setResult({ ...res, source: sourceConfig })
    } catch (err) {
      setConvError(err.message)
    } finally {
      setLoading(false)
    }
  }, [
    sourceConfig,
    sourceFilename,
    targetPlatform,
    sourceVersion,
    targetVersion,
    interfaceMap,
    custom5505,
    convertNames,
    debug,
    bootSystem,
    contextMode,
    virtualInterfaces,
  ])

  const viewerContent = viewerMode === 'source'
    ? result?.source
    : viewerMode === 'target'
    ? result?.output
    : result?.log

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      {/* Header */}
      <Header version={version} />

      {/* API error banner */}
      {apiError && (
        <div className="panel bg-red-50 border-red-300 mb-4">
          <p className="text-sm text-red-700">
            <strong>API error:</strong> {apiError} — is the pix2asa server
            running? (<code>pix2asa --serve</code>)
          </p>
        </div>
      )}

      {/* Step 1: Source config */}
      <ConfigInput value={sourceConfig} onChange={setSourceConfig} onFilename={setSourceFilename} />
      <StatusBar config={sourceConfig} />

      {/* Step 2: Target device */}
      <DeviceSelector
        devices={devices}
        value={targetPlatform}
        onChange={setTargetPlatform}
      />

      {/* Step 3: Interface mapping (shows as soon as config is loaded) */}
      {sourceConfig && (
        <InterfaceMapper
          config={sourceConfig}
          device={selectedDevice}
          interfaceMap={interfaceMap}
          onChange={setInterfaceMap}
          contextMode={contextMode}
          onContextModeChange={(val) => {
            setContextMode(val)
            if (val) setTargetPlatform('custom')
          }}
          virtualInterfaces={virtualInterfaces}
          onVirtualInterfacesChange={setVirtualInterfaces}
        />
      )}

      {/* Step 4: Convert */}
      {sourceConfig && (
        <ConversionPanel
          disabled={!canConvert}
          loading={loading}
          bootSystem={bootSystem}
          onBootSystemChange={setBootSystem}
          sourceVersion={sourceVersion}
          onSourceVersionChange={(v) => { setSourceVersion(v); setVersionAutoDetected(false) }}
          versionAutoDetected={versionAutoDetected}
          targetVersion={targetVersion}
          onTargetVersionChange={setTargetVersion}
          custom5505={custom5505}
          onCustom5505Change={setCustom5505}
          convertNames={convertNames}
          onConvertNamesChange={setConvertNames}
          debug={debug}
          onDebugChange={setDebug}
          result={result}
          onConvert={handleConvert}
          onView={setViewerMode}
        />
      )}

      {/* Conversion error */}
      {convError && (
        <div className="panel bg-red-50 border-red-300">
          <p className="text-sm text-red-700">
            <strong>Conversion error:</strong> {convError}
          </p>
        </div>
      )}

      {/* Config viewer modal */}
      {viewerMode && (
        <ConfigViewer
          mode={viewerMode}
          content={viewerContent}
          onClose={() => setViewerMode(null)}
        />
      )}
    </div>
  )
}
