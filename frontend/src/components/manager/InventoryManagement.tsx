import React, { useState, useMemo } from 'react';
import {
  Search,
  ArrowUpDown,
  History,
  AlertTriangle,
  XCircle,
  CheckCircle,
  X,
  RefreshCw,
} from 'lucide-react';
import type { ManagerProduct, StockResponse } from '../../types';
import { getProductImage } from '../../utils/format';

interface InventoryManagementProps {
  products: ManagerProduct[];
  inventory: StockResponse[];
  onOpenAdjustModal: (product: ManagerProduct) => void;
  onOpenHistoryModal: (product: ManagerProduct) => void;
  onRefresh: () => void;
}

export const InventoryManagement: React.FC<InventoryManagementProps> = ({
  products,
  inventory,
  onOpenAdjustModal,
  onOpenHistoryModal,
  onRefresh,
}) => {
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'ALL' | 'LOW_STOCK' | 'OUT_OF_STOCK'>('ALL');

  // Match inventory stock rows with product catalog metadata
  const enrichedInventory = useMemo(() => {
    return inventory.map((inv) => {
      const product = products.find((p) => p.id === inv.product_id);
      return {
        ...inv,
        product,
        name: product?.name || `Product SKU: ${inv.product_id.slice(0, 8)}`,
        sku: product?.sku || 'UNKNOWN',
        category: product?.category || 'Grocery',
      };
    });
  }, [inventory, products]);

  // Filter items based on search and active tab
  const filteredInventory = useMemo(() => {
    return enrichedInventory.filter((item) => {
      const q = searchTerm.toLowerCase().trim();
      const matchesSearch =
        !q ||
        item.name.toLowerCase().includes(q) ||
        item.sku.toLowerCase().includes(q);

      if (!matchesSearch) return false;

      if (activeTab === 'LOW_STOCK') {
        return item.is_low_stock || item.qty_available <= item.low_stock_threshold;
      }
      if (activeTab === 'OUT_OF_STOCK') {
        return item.qty_available <= 0;
      }
      return true;
    });
  }, [enrichedInventory, searchTerm, activeTab]);

  return (
    <div className="space-y-4">
      {/* 1. Header Toolbar & Tab Switcher */}
      <div className="p-4 sm:p-5 rounded-2xl bg-white border border-gray-200/90 shadow-xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Tabs */}
        <div className="flex items-center gap-1.5 p-1 bg-gray-100 rounded-xl self-start">
          <button
            type="button"
            onClick={() => setActiveTab('ALL')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === 'ALL'
                ? 'bg-white text-gray-900 shadow-xs'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            All Inventory ({enrichedInventory.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('LOW_STOCK')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeTab === 'LOW_STOCK'
                ? 'bg-amber-500 text-white shadow-xs'
                : 'text-amber-800 hover:text-amber-900'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            <span>Low Stock ({enrichedInventory.filter((i) => i.is_low_stock).length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('OUT_OF_STOCK')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeTab === 'OUT_OF_STOCK'
                ? 'bg-red-600 text-white shadow-xs'
                : 'text-red-700 hover:text-red-900'
            }`}
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Out of Stock ({enrichedInventory.filter((i) => i.qty_available <= 0).length})</span>
          </button>
        </div>

        {/* Search & Refresh */}
        <div className="flex items-center gap-2.5">
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Filter inventory SKU or name..."
              className="w-full pl-9 pr-8 py-1.5 text-xs border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-gray-50/50"
            />
            {searchTerm && (
              <button
                onClick={() => setSearchTerm('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-0.5"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            className="p-2 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-50 transition"
            title="Refresh inventory from database"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. Inventory Table */}
      <div className="bg-white rounded-2xl border border-gray-200/90 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50/70 text-gray-500 font-semibold uppercase text-[11px] tracking-wider">
                <th className="py-3 px-4">Product & SKU</th>
                <th className="py-3 px-4 text-center">Physical On-Hand</th>
                <th className="py-3 px-4 text-center">Reserved (10-Min Hold)</th>
                <th className="py-3 px-4 text-center">Available Stock</th>
                <th className="py-3 px-4 text-center">Threshold</th>
                <th className="py-3 px-4">Stock Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredInventory.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-gray-400">
                    <p className="font-semibold text-gray-700">No inventory matches found</p>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      All products may be adequately stocked or filter is active.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredInventory.map((item) => {
                  const img =
                    item.product?.image?.secure_url ||
                    getProductImage(item.sku, item.category);

                  const isOut = item.qty_available <= 0;
                  const isLow = !isOut && (item.is_low_stock || item.qty_available <= item.low_stock_threshold);

                  return (
                    <tr
                      key={item.product_id}
                      className={`hover:bg-gray-50/80 transition ${
                        isOut ? 'bg-red-50/30' : isLow ? 'bg-amber-50/20' : ''
                      }`}
                    >
                      {/* Product Thumbnail & Name */}
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <img
                            src={img}
                            alt={item.name}
                            className="w-10 h-10 rounded-lg object-cover bg-gray-50 border border-gray-200 shrink-0"
                          />
                          <div className="min-w-0 max-w-xs">
                            <p className="font-bold text-gray-900 truncate text-xs sm:text-sm">
                              {item.name}
                            </p>
                            <p className="font-mono text-[11px] text-gray-400">{item.sku}</p>
                          </div>
                        </div>
                      </td>

                      {/* Physical On-Hand */}
                      <td className="py-3 px-4 text-center font-bold text-gray-900">
                        {item.qty_on_hand}
                      </td>

                      {/* Reserved Holds */}
                      <td className="py-3 px-4 text-center font-semibold text-amber-700">
                        {item.qty_reserved > 0 ? (
                          <span className="px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 text-[11px]">
                            {item.qty_reserved} held
                          </span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>

                      {/* Available Stock */}
                      <td className="py-3 px-4 text-center">
                        <span
                          className={`font-black text-sm px-2.5 py-1 rounded-full ${
                            isOut
                              ? 'bg-red-100 text-red-800'
                              : isLow
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {item.qty_available}
                        </span>
                      </td>

                      {/* Low-Stock Threshold */}
                      <td className="py-3 px-4 text-center text-gray-500 font-mono">
                        ≤ {item.low_stock_threshold}
                      </td>

                      {/* Status Badge */}
                      <td className="py-3 px-4">
                        {isOut ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-800">
                            <XCircle className="w-3 h-3" />
                            <span>Out of Stock</span>
                          </span>
                        ) : isLow ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
                            <AlertTriangle className="w-3 h-3" />
                            <span>Low Stock</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                            <CheckCircle className="w-3 h-3" />
                            <span>Sufficient</span>
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {item.product && (
                            <>
                              <button
                                type="button"
                                onClick={() => onOpenAdjustModal(item.product!)}
                                className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-[11px] shadow-xs transition flex items-center gap-1"
                                title="Adjust stock count with audit reason"
                              >
                                <ArrowUpDown className="w-3 h-3" />
                                <span>Adjust</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => onOpenHistoryModal(item.product!)}
                                className="p-1 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100 transition"
                                title="View PostgreSQL inventory audit history"
                              >
                                <History className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
