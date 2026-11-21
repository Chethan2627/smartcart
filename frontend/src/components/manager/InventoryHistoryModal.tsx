import React, { useState, useEffect } from 'react';
import { X, History, ArrowRight, ShieldCheck, Loader2 } from 'lucide-react';
import type { ManagerProduct, InventoryAuditLog } from '../../types';
import { fetchInventoryHistory } from '../../api/client';

interface InventoryHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  product: ManagerProduct | null;
  storeId?: string;
}

export const InventoryHistoryModal: React.FC<InventoryHistoryModalProps> = ({
  isOpen,
  onClose,
  product,
  storeId,
}) => {
  const [logs, setLogs] = useState<InventoryAuditLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !product) {
      return;
    }

    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) {
        setLoading(true);
        setError(null);
      }
    });

    fetchInventoryHistory(product.id, storeId, 0, 50)
      .then((history) => {
        if (!cancelled) {
          setLogs(history);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          console.error('Fetch history error:', err);
          setError(err instanceof Error ? err.message : 'Failed to load inventory history');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, product, storeId]);

  if (!isOpen || !product) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/60 backdrop-blur-sm overflow-y-auto animate-fade-in">
      <div
        className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-gray-100 bg-gray-50/70 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">Inventory Audit Trail</h3>
              <p className="text-xs text-gray-500 font-mono">
                {product.name} ({product.sku})
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* PostgreSQL Trigger notice */}
        <div className="px-5 py-2.5 bg-emerald-50/60 border-b border-emerald-100 flex items-center gap-2 text-xs text-emerald-800">
          <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>
            Immutable PostgreSQL audit ledger triggered automatically on all inventory mutations.
          </span>
        </div>

        {/* Table / List */}
        <div className="p-5 sm:p-6 max-h-[70vh] overflow-y-auto">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-gray-400 gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-emerald-600" />
              <span className="text-xs">Loading historical log entries...</span>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-red-50 text-red-700 text-xs text-center">{error}</div>
          ) : logs.length === 0 ? (
            <div className="py-12 text-center text-gray-400">
              <History className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-xs font-semibold text-gray-700">No inventory changes recorded yet</p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                Mutations from customer orders or manager adjustments will appear here.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 rounded-xl border border-gray-200 overflow-hidden">
              {logs.map((log) => {
                const delta = log.new_on_hand - log.old_on_hand;
                const formattedDate = new Date(log.changed_at).toLocaleString('en-IN', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                });

                return (
                  <div key={log.id} className="p-3.5 hover:bg-gray-50/80 transition flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 font-mono text-[11px]">
                        <span className="text-gray-400">{formattedDate}</span>
                        <span className="font-semibold text-gray-700">Log #{log.id}</span>
                      </div>
                      <p className="font-medium text-gray-900">
                        Reason: <span className="text-gray-700 font-normal">{log.reason}</span>
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {/* Physical Stock Delta */}
                      <div className="p-2 rounded-lg bg-gray-50 border border-gray-200 text-center min-w-28">
                        <span className="text-[10px] text-gray-400 block uppercase font-semibold">On-Hand</span>
                        <div className="flex items-center justify-center gap-1 font-bold">
                          <span className="text-gray-500">{log.old_on_hand}</span>
                          <ArrowRight className="w-3 h-3 text-gray-400" />
                          <span className="text-gray-900">{log.new_on_hand}</span>
                          <span
                            className={`ml-1 text-[10px] font-extrabold ${
                              delta > 0
                                ? 'text-emerald-700'
                                : delta < 0
                                ? 'text-red-700'
                                : 'text-gray-500'
                            }`}
                          >
                            ({delta >= 0 ? `+${delta}` : delta})
                          </span>
                        </div>
                      </div>

                      {/* Reserved Stock */}
                      <div className="p-2 rounded-lg bg-gray-50 border border-gray-200 text-center min-w-24">
                        <span className="text-[10px] text-gray-400 block uppercase font-semibold">Reserved</span>
                        <div className="flex items-center justify-center gap-1 font-bold text-amber-700">
                          <span>{log.old_reserved}</span>
                          <ArrowRight className="w-3 h-3 text-gray-400" />
                          <span>{log.new_reserved}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
