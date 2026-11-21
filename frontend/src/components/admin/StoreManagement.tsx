import React, { useState } from 'react';
import {
  MapPin,
  CheckCircle2,
  XCircle,
  Copy,
  Search,
  Check,
  Building2,
  Layers,
} from 'lucide-react';
import type { Store } from '../../types';

interface StoreManagementProps {
  stores: Store[];
  onSelectStoreContext: (store: Store) => void;
  onNavigateToManager: () => void;
}

export const StoreManagement: React.FC<StoreManagementProps> = ({
  stores,
  onSelectStoreContext,
  onNavigateToManager,
}) => {
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState<string>('ALL');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedDetailStore, setSelectedDetailStore] = useState<Store | null>(null);

  const states = Array.from(new Set(stores.map((s) => s.state).filter(Boolean)));

  const filteredStores = stores.filter((s) => {
    const matchesSearch =
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.code.toLowerCase().includes(search.toLowerCase()) ||
      s.city.toLowerCase().includes(search.toLowerCase());
    const matchesState = stateFilter === 'ALL' || s.state === stateFilter;
    return matchesSearch && matchesState;
  });

  const handleCopyId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Fulfillment Stores Network
          </h2>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Manage physical micro-warehouses and quick-commerce dark stores across India.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs font-bold">
            {stores.length} Configured Stores
          </span>
        </div>
      </div>

      {/* Search & Filter Controls */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search stores by name, city, or store code..."
            className="w-full pl-10 pr-4 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
        </div>

        <select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className="w-full sm:w-48 py-2.5 px-3 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-300 focus:outline-none focus:border-purple-500"
        >
          <option value="ALL">All States ({stores.length})</option>
          {states.map((st) => (
            <option key={st} value={st}>
              State: {st}
            </option>
          ))}
        </select>
      </div>

      {/* Stores Network Table */}
      <div className="bg-slate-900/80 rounded-3xl border border-slate-800/80 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-900/90 border-b border-slate-800 text-[11px] uppercase font-bold text-slate-400 tracking-wider">
              <tr>
                <th className="p-4">Store / Code</th>
                <th className="p-4">Location</th>
                <th className="p-4">Status</th>
                <th className="p-4">Store UUID</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {filteredStores.map((store) => (
                <tr key={store.id} className="hover:bg-slate-800/40 transition">
                  {/* Name & Code */}
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center shrink-0">
                        <Building2 className="w-5 h-5" />
                      </div>
                      <div>
                        <p className="font-bold text-white text-sm">{store.name}</p>
                        <p className="text-[11px] text-purple-400 font-mono">
                          Code: {store.code}
                        </p>
                      </div>
                    </div>
                  </td>

                  {/* Location */}
                  <td className="p-4">
                    <div className="flex items-start gap-1.5">
                      <MapPin className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                      <div>
                        <p className="text-slate-200 font-semibold">{store.city}, {store.state}</p>
                        <p className="text-[11px] text-slate-400 max-w-xs truncate">
                          {store.address || 'Standard fulfillment warehouse'}
                        </p>
                      </div>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="p-4">
                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold ${
                        store.is_active
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      }`}
                    >
                      {store.is_active ? (
                        <>
                          <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                          <span>Active Hub</span>
                        </>
                      ) : (
                        <>
                          <XCircle className="w-3 h-3 text-rose-400" />
                          <span>Inactive</span>
                        </>
                      )}
                    </span>
                  </td>

                  {/* UUID with Copy */}
                  <td className="p-4">
                    <div className="flex items-center gap-2 font-mono text-[11px] text-slate-400">
                      <span>{store.id.slice(0, 13)}...</span>
                      <button
                        type="button"
                        onClick={() => handleCopyId(store.id)}
                        className="p-1 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition"
                        title="Copy Full UUID"
                      >
                        {copiedId === store.id ? (
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>
                  </td>

                  {/* Actions */}
                  <td className="p-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedDetailStore(store)}
                        className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition"
                      >
                        Details
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          onSelectStoreContext(store);
                          onNavigateToManager();
                        }}
                        className="px-3 py-1.5 rounded-lg bg-purple-600/30 hover:bg-purple-600 text-purple-200 hover:text-white border border-purple-500/30 text-xs font-semibold transition flex items-center gap-1.5"
                        title="Open store in Manager View"
                      >
                        <Layers className="w-3 h-3" />
                        <span>Manage Store</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Store Detail Modal */}
      {selectedDetailStore && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div
            className="relative w-full max-w-lg bg-slate-900 rounded-3xl border border-slate-800 p-6 space-y-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center font-bold">
                  <Building2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-white text-base">{selectedDetailStore.name}</h3>
                  <p className="text-xs text-purple-400 font-mono">Store Code: {selectedDetailStore.code}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDetailStore(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800 space-y-1">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Store Full UUID</span>
                <p className="font-mono text-purple-300 break-all select-all">{selectedDetailStore.id}</p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">City & State</span>
                  <p className="font-bold text-slate-200 mt-0.5">{selectedDetailStore.city}, {selectedDetailStore.state}</p>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800">
                  <span className="text-[10px] text-slate-500 uppercase font-semibold">Status</span>
                  <p className="font-bold text-emerald-400 mt-0.5">
                    {selectedDetailStore.is_active ? 'Active & Fulfilling' : 'Inactive'}
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800 space-y-1">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Warehouse Delivery Address</span>
                <p className="text-slate-300">{selectedDetailStore.address || 'Address registered in PostgreSQL store registry'}</p>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setSelectedDetailStore(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => {
                  onSelectStoreContext(selectedDetailStore);
                  setSelectedDetailStore(null);
                  onNavigateToManager();
                }}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold shadow-md shadow-purple-600/30 flex items-center gap-1.5"
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Open in Manager Portal</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
