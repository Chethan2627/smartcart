import React from 'react';
import {
  Package,
  Layers,
  AlertTriangle,
  XCircle,
  Plus,
  ArrowRight,
  Store,
  MapPin,
  TrendingUp,
} from 'lucide-react';
import type { ManagerProduct, StockResponse, Store as StoreType } from '../../types';
import { getProductImage } from '../../utils/format';

interface ManagerOverviewProps {
  products: ManagerProduct[];
  inventory: StockResponse[];
  lowStockItems: StockResponse[];
  store: StoreType | null;
  onOpenAdjustModal: (product: ManagerProduct) => void;
  onNavigateToProducts: () => void;
  onNavigateToInventory: () => void;
  onOpenAddProduct: () => void;
}

export const ManagerOverview: React.FC<ManagerOverviewProps> = ({
  products,
  inventory,
  lowStockItems,
  store,
  onOpenAdjustModal,
  onNavigateToProducts,
  onNavigateToInventory,
  onOpenAddProduct,
}) => {
  const totalProducts = products.length;
  const totalOnHandUnits = inventory.reduce((sum, item) => sum + item.qty_on_hand, 0);
  const totalReservedUnits = inventory.reduce((sum, item) => sum + item.qty_reserved, 0);
  const outOfStockCount = inventory.filter((item) => item.qty_available <= 0).length;

  return (
    <div className="space-y-6">
      {/* 1. Store Profile & Quick Actions Banner */}
      <div className="p-6 bg-gradient-to-r from-slate-900 via-slate-800 to-emerald-950 rounded-3xl text-white shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-semibold mb-2 border border-emerald-500/30">
            <Store className="w-3.5 h-3.5" />
            <span>Assigned Store Location</span>
          </div>
          <h2 className="text-2xl font-black tracking-tight">{store?.name || 'SmartCart Bengaluru'}</h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300 mt-1">
            <span className="font-mono bg-white/10 px-2 py-0.5 rounded">
              Code: {store?.code || 'STORE-001'}
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="w-3 h-3 text-emerald-400" />
              {store?.city || 'Bengaluru'}, {store?.state || 'Karnataka'}
            </span>
            <span className="text-emerald-400 font-semibold">• Live Operations</span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2.5">
          <button
            type="button"
            onClick={onOpenAddProduct}
            className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-md transition flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>New Product</span>
          </button>
          <button
            type="button"
            onClick={onNavigateToInventory}
            className="px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold text-xs transition border border-white/10 flex items-center gap-2"
          >
            <span>Audit Inventory</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. Key Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Products */}
        <div
          onClick={onNavigateToProducts}
          className="p-5 rounded-2xl bg-white border border-gray-200/80 shadow-xs hover:shadow-md hover:border-emerald-300 transition cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Total Products
            </span>
            <div className="w-9 h-9 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center group-hover:scale-110 transition">
              <Package className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-gray-900">{totalProducts}</span>
            <span className="text-xs text-gray-400">SKUs in catalog</span>
          </div>
          <span className="mt-2 text-[11px] text-emerald-600 font-semibold block flex items-center gap-1">
            <span>View all products</span>
            <ArrowRight className="w-3 h-3" />
          </span>
        </div>

        {/* Total Units On Hand */}
        <div
          onClick={onNavigateToInventory}
          className="p-5 rounded-2xl bg-white border border-gray-200/80 shadow-xs hover:shadow-md hover:border-emerald-300 transition cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Inventory Balance
            </span>
            <div className="w-9 h-9 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center group-hover:scale-110 transition">
              <Layers className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-black text-gray-900">{totalOnHandUnits}</span>
            <span className="text-xs text-gray-400">physical units</span>
          </div>
          <span className="mt-2 text-[11px] text-gray-500 font-medium block">
            {totalReservedUnits} units held in active 10-min reservations
          </span>
        </div>

        {/* Low-Stock Alerts */}
        <div className="p-5 rounded-2xl bg-white border border-gray-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Low-Stock Warnings
            </span>
            <div className="w-9 h-9 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span
              className={`text-3xl font-black ${
                lowStockItems.length > 0 ? 'text-amber-600' : 'text-gray-900'
              }`}
            >
              {lowStockItems.length}
            </span>
            <span className="text-xs text-gray-400">require re-order</span>
          </div>
          <span className="mt-2 text-[11px] text-amber-600 font-semibold block">
            {lowStockItems.length > 0 ? 'Available stock ≤ threshold' : 'All stock levels optimal'}
          </span>
        </div>

        {/* Out-of-Stock Items */}
        <div className="p-5 rounded-2xl bg-white border border-gray-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Out of Stock
            </span>
            <div className="w-9 h-9 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center">
              <XCircle className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span
              className={`text-3xl font-black ${
                outOfStockCount > 0 ? 'text-rose-600' : 'text-gray-900'
              }`}
            >
              {outOfStockCount}
            </span>
            <span className="text-xs text-gray-400">zero availability</span>
          </div>
          <span className="mt-2 text-[11px] text-rose-600 font-semibold block">
            {outOfStockCount > 0 ? 'Immediate re-stock needed' : 'Zero sold-out items'}
          </span>
        </div>
      </div>

      {/* 3. Priority Low-Stock Action Table */}
      <div className="bg-white rounded-2xl border border-gray-200/90 shadow-xs overflow-hidden">
        <div className="p-5 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-amber-600" />
            <h3 className="font-bold text-gray-900 text-sm">
              Stock Re-order Priority Attention ({lowStockItems.length})
            </h3>
          </div>
          <button
            type="button"
            onClick={onNavigateToInventory}
            className="text-xs font-semibold text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
          >
            <span>Full Inventory View</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {lowStockItems.length === 0 ? (
          <div className="p-8 text-center text-gray-400 text-xs">
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 opacity-30 text-emerald-600" />
            <p className="font-semibold text-gray-700">Healthy Inventory Status</p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              No store products currently breach their low-stock thresholds.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100 overflow-x-auto">
            {lowStockItems.map((item) => {
              const matchedProduct = products.find((p) => p.id === item.product_id);
              const name = matchedProduct?.name || `Product SKU: ${item.product_id.slice(0, 8)}`;
              const sku = matchedProduct?.sku || 'UNKNOWN';
              const img = matchedProduct?.image?.secure_url || getProductImage(sku, matchedProduct?.category);

              return (
                <div
                  key={item.product_id}
                  className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-gray-50/80 transition text-xs"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <img
                      src={img}
                      alt={name}
                      className="w-11 h-11 rounded-lg object-cover bg-gray-50 border border-gray-200 shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="font-bold text-gray-900 truncate text-sm">{name}</p>
                      <p className="text-[11px] text-gray-400 font-mono">
                        SKU: {sku} • Threshold: {item.low_stock_threshold} units
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 shrink-0 justify-between sm:justify-end">
                    <div className="text-right">
                      <span className="text-[10px] text-gray-400 uppercase font-semibold block">Available</span>
                      <span
                        className={`text-sm font-extrabold ${
                          item.qty_available === 0 ? 'text-red-600' : 'text-amber-600'
                        }`}
                      >
                        {item.qty_available} units
                      </span>
                    </div>

                    {matchedProduct && (
                      <button
                        type="button"
                        onClick={() => onOpenAdjustModal(matchedProduct)}
                        className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-xs transition"
                      >
                        Adjust Stock
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
