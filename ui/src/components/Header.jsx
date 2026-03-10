import { useState } from 'react'

export default function Header({ version }) {
  const [showAbout, setShowAbout] = useState(false)

  return (
    <div className="panel">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h1 className="text-xl font-bold text-blue-800 mb-1">
            PIX to ASA Migration Tool
          </h1>
          <p className="text-sm text-gray-700 leading-relaxed max-w-3xl">
            This tool converts a Cisco PIX firewall configuration to a Cisco
            Adaptive Security Appliance (ASA) configuration. Select a source
            configuration file, choose your target ASA device, map the
            interfaces, then click <strong>Make target configuration</strong>.
          </p>
        </div>
        <button
          className="btn btn-secondary ml-4 text-xs"
          onClick={() => setShowAbout(true)}
        >
          About
        </button>
      </div>

      {showAbout && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded border border-gray-300 shadow-lg p-6 max-w-sm w-full">
            <h2 className="text-base font-bold mb-3">
              PIX to ASA Migration Tool
            </h2>
            <p className="text-sm mb-1">
              <span className="font-medium">Version:</span>{' '}
              {version ?? 'unknown'}
            </p>
            <p className="text-sm mb-1">
              <span className="font-medium">Python package:</span> pix2asa
            </p>
            <p className="text-sm text-gray-500 mt-3">
              Modernised as a Python 3 / React application.
            </p>
            <div className="mt-4 text-right">
              <button
                className="btn btn-primary"
                onClick={() => setShowAbout(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
