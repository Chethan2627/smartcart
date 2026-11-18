import { useState, useEffect } from 'react'
import { fetchHealth, fetchRoot } from './api/client'
import type { SystemHealthResponse, RootResponse } from './api/client'
import { CheckCircle2, AlertCircle, RefreshCw, Server, Database, Activity, ExternalLink, ShieldCheck } from 'lucide-react'

export function App() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [rootInfo, setRootInfo] = useState<RootResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const checkBackendStatus = async () => {
    setLoading(true)
    setError(null)
    try {
      const [healthData, rootData] = await Promise.all([
        fetchHealth(),
        fetchRoot(),
      ])
      setHealth(healthData)
      setRootInfo(rootData)
    } catch (err: any) {
      setError(err?.message || 'Failed to connect to FastAPI backend at http://localhost:8000')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkBackendStatus()
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500 selection:text-white">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center font-bold text-xl text-white shadow-lg shadow-indigo-500/25">
            S
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-lg text-white tracking-tight">SmartCart</span>
              <span className="text-xs bg-indigo-500/20 text-indigo-400 font-semibold px-2 py-0.5 rounded-full border border-indigo-500/30">
                v2.0
              </span>
            </div>
            <p className="text-xs text-slate-400">Team Hack Hive • CIT Gubbi</p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center space-x-1.5 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-700 transition"
          >
            <ExternalLink className="w-3.5 h-3.5 text-indigo-400" />
            <span>FastAPI Swagger Docs</span>
          </a>
          <button
            onClick={checkBackendStatus}
            disabled={loading}
            className="flex items-center space-x-1.5 text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg shadow-sm transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Check Connectivity</span>
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-12 flex flex-col items-center justify-center text-center">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-medium mb-6">
          <Activity className="w-3.5 h-3.5 text-indigo-400" />
          <span>Phase 0: Project Foundation Active</span>
        </div>

        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white max-w-3xl leading-tight">
          Smarter Discovery. Reliable Inventory. <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-violet-400 to-pink-400">
            Seamless Shopping.
          </span>
        </h1>

        <p className="mt-4 text-base sm:text-lg text-slate-400 max-w-2xl">
          Multi-store intelligent retail platform powered by Aiven cloud infrastructure. Built for zero overselling, typo-tolerant search, and asynchronous event-driven orders.
        </p>

        {/* Connectivity Status Banner */}
        <div className="w-full max-w-3xl mt-10 p-6 rounded-2xl bg-slate-900 border border-slate-800 shadow-xl text-left">
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <div className="flex items-center space-x-2">
              <Server className="w-5 h-5 text-indigo-400" />
              <h2 className="text-base font-semibold text-white">Full-Stack Connectivity Status</h2>
            </div>
            <div className="flex items-center space-x-2">
              {loading ? (
                <span className="inline-flex items-center text-xs text-yellow-400 bg-yellow-400/10 px-2.5 py-1 rounded-full border border-yellow-400/20">
                  <RefreshCw className="w-3 h-3 animate-spin mr-1.5" /> Checking backend...
                </span>
              ) : error ? (
                <span className="inline-flex items-center text-xs text-rose-400 bg-rose-400/10 px-2.5 py-1 rounded-full border border-rose-400/20">
                  <AlertCircle className="w-3 h-3 mr-1.5" /> Backend Unreachable
                </span>
              ) : (
                <span className="inline-flex items-center text-xs text-emerald-400 bg-emerald-400/10 px-2.5 py-1 rounded-full border border-emerald-400/20">
                  <CheckCircle2 className="w-3 h-3 mr-1.5" /> Frontend & Backend Connected
                </span>
              )}
            </div>
          </div>

          {error ? (
            <div className="mt-4 p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm flex items-start space-x-3">
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Connection Error</p>
                <p className="text-xs text-rose-400 mt-1">{error}</p>
                <p className="text-xs text-slate-400 mt-2">
                  Ensure the FastAPI backend server is running via{' '}
                  <code className="text-slate-300 bg-slate-800 px-1 py-0.5 rounded">
                    uvicorn app.main:app --port 8000
                  </code>
                </p>
              </div>
            </div>
          ) : health ? (
            <div className="mt-4 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                  <span className="text-slate-500 block mb-1">Backend Version</span>
                  <span className="font-mono text-slate-200">{health.version}</span>
                </div>
                <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                  <span className="text-slate-500 block mb-1">Environment</span>
                  <span className="font-mono text-emerald-400 uppercase">{health.environment}</span>
                </div>
              </div>

              {/* Mandatory Architecture Services Checklist */}
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Mandatory Infrastructure (Aiven Services)
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Database className="w-4 h-4 text-blue-400" />
                      <span className="text-xs text-slate-300 font-medium">PostgreSQL</span>
                    </div>
                    <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">Phase 1</span>
                  </div>

                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Activity className="w-4 h-4 text-purple-400" />
                      <span className="text-xs text-slate-300 font-medium">Apache Kafka</span>
                    </div>
                    <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">Phase 1/5</span>
                  </div>

                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800 flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <ShieldCheck className="w-4 h-4 text-amber-400" />
                      <span className="text-xs text-slate-300 font-medium">OpenSearch</span>
                    </div>
                    <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">Phase 1/6</span>
                  </div>
                </div>
              </div>

              {rootInfo && (
                <div className="p-3 rounded-xl bg-indigo-950/20 border border-indigo-900/30 text-xs text-indigo-300">
                  <span className="font-semibold text-white">Project Verified: </span>
                  {rootInfo.project} — {rootInfo.institution}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-6 text-center text-xs text-slate-500">
        <p>SmartCart 2.0 • Hack Hive • Channabasaveshwara Institute of Technology (CIT), Gubbi</p>
        <p className="mt-1">Build Bangalore 2.0 Hackathon • Powered by Aiven</p>
      </footer>
    </div>
  )
}

export default App
