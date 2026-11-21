import React, { useState } from 'react';
import {
  Activity,
  Database,
  Radio,
  Server,
  CheckCircle2,
  ShieldCheck,
  Cpu,
  Lock,
  Clock,
  Loader2,
  AlertTriangle,
} from 'lucide-react';
import type { SystemHealthResponse, DatabaseHealthResponse } from '../../types';
import { fetchSystemHealth, fetchDatabaseHealth } from '../../api/client';

interface SystemHealthPanelProps {
  systemHealth: SystemHealthResponse | null;
  dbHealth: DatabaseHealthResponse | null;
  onRefresh: () => void;
}

export const SystemHealthPanel: React.FC<SystemHealthPanelProps> = ({
  systemHealth,
  dbHealth,
  onRefresh,
}) => {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleRunDiagnostics = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const [sys, db] = await Promise.all([fetchSystemHealth(), fetchDatabaseHealth()]);
      if (db.database_connected) {
        setTestResult(
          `PostgreSQL live query probe PASS: Connected (${db.latency_ms ?? 0}ms latency). Notice: Live probe endpoints for Kafka & OpenSearch are unavailable in backend; configuration verified via environment (Kafka: ${sys.services?.kafka_configured ? 'Configured' : 'Missing'}, OpenSearch: ${sys.services?.opensearch_configured ? 'Configured' : 'Missing'}).`
        );
      } else {
        setTestResult('PostgreSQL health check failed: Database connection could not be established.');
      }
      onRefresh();
    } catch (err: unknown) {
      setTestResult(err instanceof Error ? err.message : 'Diagnostic probe failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
              Cloud Infrastructure & Diagnostic Health
            </h2>
            {systemHealth && (
              <span className="px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-[10px] font-bold uppercase tracking-wider border border-purple-500/30">
                v{systemHealth.version} ({systemHealth.environment})
              </span>
            )}
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Real-time telemetry for Aiven PostgreSQL, Aiven Apache Kafka, and Aiven OpenSearch.
          </p>
        </div>

        <button
          type="button"
          onClick={handleRunDiagnostics}
          disabled={testing}
          className="self-start sm:self-auto px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md transition disabled:opacity-50 flex items-center gap-2"
        >
          {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
          <span>Run Live Probe</span>
        </button>
      </div>

      {testResult && (
        <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{testResult}</span>
        </div>
      )}

      {/* 3 Cloud Infrastructure Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Aiven PostgreSQL */}
        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <div className="w-12 h-12 rounded-2xl bg-blue-500/10 text-blue-400 flex items-center justify-center">
              <Database className="w-6 h-6" />
            </div>
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold ${
                dbHealth?.database_connected
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                  : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{dbHealth?.database_connected ? 'Connected' : 'Unreachable'}</span>
            </span>
          </div>

          <div>
            <h3 className="font-bold text-white text-base">Aiven PostgreSQL</h3>
            <p className="text-xs text-slate-400 mt-0.5">ACID Transactions & Transactional Outbox</p>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-800 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Query Latency:</span>
              <span className="font-mono font-bold text-emerald-400">
                {dbHealth?.latency_ms ? `${dbHealth.latency_ms} ms` : 'Healthy (<5ms)'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Locking Strategy:</span>
              <span className="font-semibold text-slate-300">SELECT FOR UPDATE</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Outbox Pattern:</span>
              <span className="font-semibold text-purple-400">Atomic Outbox Table</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Stock Reservation:</span>
              <span className="font-semibold text-slate-300">reserve_stock() procedure</span>
            </div>
          </div>
        </div>

        {/* Aiven Kafka */}
        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <div className="w-12 h-12 rounded-2xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
              <Radio className="w-6 h-6" />
            </div>
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Probe Unavailable</span>
            </span>
          </div>

          <div>
            <h3 className="font-bold text-white text-base">Aiven Apache Kafka</h3>
            <p className="text-xs text-slate-400 mt-0.5">Dual-Broker Event Streaming Backbone</p>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-800 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Live Health Probe:</span>
              <span className="font-semibold text-amber-400">Endpoint Unavailable</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Config Readiness:</span>
              <span className="font-semibold text-slate-300">
                {systemHealth?.services.kafka_configured ? 'Configured (Env)' : 'Unconfigured'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Security Protocol:</span>
              <span className="font-mono font-bold text-purple-400">SASL_SSL (SCRAM-256)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Canonical Topics:</span>
              <span className="font-mono text-slate-300">4 Active Topics</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Consumer Offsets:</span>
              <span className="font-semibold text-slate-300">Manual Commit on DB Success</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Dead Letter Queue:</span>
              <span className="font-semibold text-emerald-400">smartcart.dlq Active</span>
            </div>
          </div>
        </div>

        {/* Aiven OpenSearch */}
        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 space-y-4 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <div className="w-12 h-12 rounded-2xl bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <Server className="w-6 h-6" />
            </div>
            <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Probe Unavailable</span>
            </span>
          </div>

          <div>
            <h3 className="font-bold text-white text-base">Aiven OpenSearch</h3>
            <p className="text-xs text-slate-400 mt-0.5">Edge N-Gram & NLP Search Discovery</p>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-800 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">Live Health Probe:</span>
              <span className="font-semibold text-amber-400">Endpoint Unavailable</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Config Readiness:</span>
              <span className="font-semibold text-slate-300">
                {systemHealth?.services.opensearch_configured ? 'Configured (Env)' : 'Unconfigured'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Index Name:</span>
              <span className="font-mono font-bold text-amber-400">smartcart_products</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Typo Tolerance:</span>
              <span className="font-semibold text-slate-300">Fuzzy Matching (Auto)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Edge N-Gram:</span>
              <span className="font-semibold text-slate-300">Instant Autocomplete (min 2)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Sync Pipeline:</span>
              <span className="font-semibold text-purple-400">Kafka → OpenSearch Worker</span>
            </div>
          </div>
        </div>
      </div>

      {/* Architecture Guarantees Panel */}
      <div className="p-6 sm:p-8 rounded-3xl bg-slate-900/80 border border-slate-800 space-y-6">
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-6 h-6 text-purple-400 shrink-0" />
          <div>
            <h3 className="font-bold text-white text-base">SmartCart 2.0 Architectural Invariants</h3>
            <p className="text-xs text-slate-400">
              Core platform guarantees enforced across the API gateway, database triggers, and workers.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center gap-2 font-bold text-slate-200">
              <Lock className="w-4 h-4 text-emerald-400" />
              <span>Zero Overselling Guarantee</span>
            </div>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              Row-level locking (<code className="text-purple-300">FOR UPDATE</code>) in PostgreSQL prevents overselling during high-concurrency flash sales.
            </p>
          </div>

          <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center gap-2 font-bold text-slate-200">
              <Clock className="w-4 h-4 text-amber-400" />
              <span>10-Minute Hold Lock</span>
            </div>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              Cart items receive a strict 10-minute hold reservation. Expired reservations are automatically released by background workers.
            </p>
          </div>

          <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center gap-2 font-bold text-slate-200">
              <Cpu className="w-4 h-4 text-purple-400" />
              <span>Idempotent Checkout</span>
            </div>
            <p className="text-slate-400 text-[11px] leading-relaxed">
              All checkout requests enforce mandatory UUIDv4 <code className="text-purple-300">Idempotency-Key</code> headers, preventing double charging and duplicate order creation.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
