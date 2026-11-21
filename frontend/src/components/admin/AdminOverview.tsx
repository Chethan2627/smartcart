import React from 'react';
import {
  Store as StoreIcon,
  Package,
  Layers,
  ClipboardList,
  ShieldCheck,
  Activity,
  ArrowRight,
  Server,
  Database,
  Radio,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import type { Store, ManagerProduct, OrderResponse, DatabaseHealthResponse } from '../../types';
import { formatPrice } from '../../utils/format';

interface AdminOverviewProps {
  stores: Store[];
  products: ManagerProduct[];
  orders: OrderResponse[];
  dbHealth: DatabaseHealthResponse | null;
  onNavigateTab: (tab: 'stores' | 'catalogue' | 'orders' | 'users' | 'health') => void;
  onOpenOrderModal: (order: OrderResponse) => void;
  onOpenAddProductModal: () => void;
}

export const AdminOverview: React.FC<AdminOverviewProps> = ({
  stores,
  products,
  orders,
  dbHealth,
  onNavigateTab,
  onOpenOrderModal,
  onOpenAddProductModal,
}) => {
  const activeStoresCount = stores.filter((s) => s.is_active).length;
  const activeProductsCount = products.filter((p) => p.is_active).length;

  const totalOnHand = products.reduce((acc, p) => acc + (p.qty_on_hand || 0), 0);
  const totalReserved = products.reduce((acc, p) => acc + (p.qty_reserved || 0), 0);
  const totalAvailable = products.reduce((acc, p) => acc + (p.qty_available || 0), 0);

  const pendingOrdersCount = orders.filter((o) => o.status === 'PENDING' || o.status === 'CONFIRMED').length;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Banner */}
      <div className="p-6 sm:p-8 rounded-3xl bg-gradient-to-r from-purple-900/60 via-indigo-950/70 to-slate-900 border border-purple-500/20 shadow-2xl relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/20 border border-purple-500/30 text-purple-300 text-xs font-bold uppercase tracking-wider">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Multi-Store Central Governance</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              System Administration & Operations
            </h1>
            <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
              Real-time monitoring across all fulfillment stores, product catalogue pricing, customer orders, and live Aiven cloud services.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={onOpenAddProductModal}
              className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition flex items-center gap-2"
            >
              <Package className="w-4 h-4" />
              <span>Add Catalogue Product</span>
            </button>
            <button
              type="button"
              onClick={() => onNavigateTab('health')}
              className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold text-xs transition flex items-center gap-2"
            >
              <Activity className="w-4 h-4 text-emerald-400" />
              <span>View System Health</span>
            </button>
          </div>
        </div>
      </div>

      {/* 4 Primary KPI Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        {/* Stores Card */}
        <div
          onClick={() => onNavigateTab('stores')}
          className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800/80 hover:border-purple-500/40 transition cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Stores Network</span>
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center group-hover:scale-110 transition">
              <StoreIcon className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-black text-white mt-3">{stores.length}</p>
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
            <span className="text-emerald-400 font-semibold">{activeStoresCount} Active Hubs</span>
            <span>Across India →</span>
          </div>
        </div>

        {/* Global Catalogue Card */}
        <div
          onClick={() => onNavigateTab('catalogue')}
          className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800/80 hover:border-indigo-500/40 transition cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Catalogue Products</span>
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center group-hover:scale-110 transition">
              <Package className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-black text-white mt-3">{products.length}</p>
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
            <span className="text-indigo-400 font-semibold">{activeProductsCount} Live in Storefront</span>
            <span>Manage Prices →</span>
          </div>
        </div>

        {/* Total Inventory Units */}
        <div
          onClick={() => onNavigateTab('catalogue')}
          className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800/80 hover:border-emerald-500/40 transition cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Cross-Store Inventory</span>
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center group-hover:scale-110 transition">
              <Layers className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-black text-white mt-3">{totalAvailable}</p>
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
            <span className="text-slate-300 font-semibold">{totalOnHand} On-Hand</span>
            <span className="text-amber-400 font-mono">{totalReserved} Held</span>
          </div>
        </div>

        {/* Total Orders */}
        <div
          onClick={() => onNavigateTab('orders')}
          className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800/80 hover:border-violet-500/40 transition cursor-pointer group shadow-sm"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">Fulfillment Orders</span>
            <div className="w-9 h-9 rounded-xl bg-violet-500/10 text-violet-400 flex items-center justify-center group-hover:scale-110 transition">
              <ClipboardList className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl sm:text-3xl font-black text-white mt-3">{orders.length}</p>
          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
            <span className="text-amber-400 font-semibold">{pendingOrdersCount} In Progress</span>
            <span>Order Audit →</span>
          </div>
        </div>
      </div>

      {/* Cloud Service Readiness Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* PostgreSQL */}
        <div className="p-4 rounded-2xl bg-slate-900/90 border border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-200">Aiven PostgreSQL</p>
              <p className="text-[11px] text-slate-400">ACID Transactions & Row Locks</p>
            </div>
          </div>
          <div className="text-right">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{dbHealth?.latency_ms ? `${dbHealth.latency_ms}ms` : 'Online'}</span>
            </span>
          </div>
        </div>

        {/* Kafka */}
        <div className="p-4 rounded-2xl bg-slate-900/90 border border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
              <Radio className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-200">Aiven Kafka</p>
              <p className="text-[11px] text-slate-400">SASL_SSL Event Backbone</p>
            </div>
          </div>
          <div className="text-right">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-400" title="Backend does not provide a live health probe endpoint for Kafka">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Probe Unavailable</span>
            </span>
          </div>
        </div>

        {/* OpenSearch */}
        <div className="p-4 rounded-2xl bg-slate-900/90 border border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-200">Aiven OpenSearch</p>
              <p className="text-[11px] text-slate-400">Edge N-Gram & NLP Search</p>
            </div>
          </div>
          <div className="text-right">
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-400" title="Backend does not provide a live health probe endpoint for OpenSearch">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Probe Unavailable</span>
            </span>
          </div>
        </div>
      </div>

      {/* Two Column Layout: Recent Orders & Stores Network */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Recent Orders Section */}
        <div className="bg-slate-900/80 rounded-3xl border border-slate-800/80 overflow-hidden shadow-sm">
          <div className="p-5 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <ClipboardList className="w-5 h-5 text-purple-400" />
              <h2 className="text-sm font-bold text-white">Recent Customer Orders</h2>
            </div>
            <button
              type="button"
              onClick={() => onNavigateTab('orders')}
              className="text-xs font-semibold text-purple-400 hover:text-purple-300 flex items-center gap-1 transition"
            >
              <span>View All ({orders.length})</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {orders.length === 0 ? (
            <div className="p-10 text-center text-slate-500 text-xs">
              <ClipboardList className="w-8 h-8 mx-auto mb-2 opacity-30 text-slate-400" />
              <p className="font-semibold text-slate-400">No Orders Placed Yet</p>
              <p className="text-[11px] text-slate-500 mt-1">
                Customer purchases will appear here in real time.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-800/80 overflow-x-auto">
              {orders.slice(0, 6).map((order) => {
                const storeMatch = stores.find((s) => s.id === order.store_id);
                const storeName = storeMatch?.name || 'Assigned Store';
                const formattedDate = new Date(order.created_at).toLocaleDateString('en-IN', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                });

                return (
                  <div
                    key={order.id}
                    onClick={() => onOpenOrderModal(order)}
                    className="p-4 hover:bg-slate-800/50 transition cursor-pointer flex items-center justify-between text-xs gap-3"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-slate-200">
                          {order.order_number}
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            order.status === 'CONFIRMED'
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                              : order.status === 'PENDING'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                              : order.status === 'DELIVERED'
                              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                              : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          }`}
                        >
                          {order.status}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        {storeName} • {order.items.length} items • {formattedDate}
                      </p>
                    </div>

                    <div className="text-right shrink-0">
                      <p className="font-bold text-white text-sm">
                        {formatPrice(order.total_paise)}
                      </p>
                      <span className="text-[10px] text-purple-400 font-semibold hover:underline">
                        Audit Details →
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Stores Network Overview */}
        <div className="bg-slate-900/80 rounded-3xl border border-slate-800/80 overflow-hidden shadow-sm">
          <div className="p-5 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <StoreIcon className="w-5 h-5 text-indigo-400" />
              <h2 className="text-sm font-bold text-white">Fulfillment Stores Network</h2>
            </div>
            <button
              type="button"
              onClick={() => onNavigateTab('stores')}
              className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition"
            >
              <span>Manage Stores ({stores.length})</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="divide-y divide-slate-800/80 overflow-x-auto">
            {stores.map((s) => (
              <div
                key={s.id}
                className="p-4 hover:bg-slate-800/50 transition flex items-center justify-between text-xs gap-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <p className="font-bold text-slate-200">{s.name}</p>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        s.is_active
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {s.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 font-mono">
                    Code: {s.code} • {s.city}, {s.state}
                  </p>
                </div>

                <div className="text-right shrink-0">
                  <span className="text-[11px] text-slate-400 block font-mono">
                    ID: {s.id.slice(0, 8)}...
                  </span>
                  <span className="text-[10px] font-semibold text-indigo-400">
                    Fulfillment Node
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
