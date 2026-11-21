import React, { useState } from 'react';
import {
  Package,
  Plus,
  Search,
  Edit2,
  Camera,
  Trash2,
  RefreshCw,
} from 'lucide-react';
import type { ManagerProduct, Store } from '../../types';
import { formatPrice, getProductImage } from '../../utils/format';

interface GlobalCatalogueProps {
  products: ManagerProduct[];
  selectedStore: Store | null;
  onOpenAddModal: () => void;
  onOpenEditModal: (product: ManagerProduct) => void;
  onOpenImageModal: (product: ManagerProduct) => void;
  onDeactivateProduct: (product: ManagerProduct) => void;
  onRefresh: () => void;
}

export const GlobalCatalogue: React.FC<GlobalCatalogueProps> = ({
  products,
  selectedStore,
  onOpenAddModal,
  onOpenEditModal,
  onOpenImageModal,
  onDeactivateProduct,
  onRefresh,
}) => {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'INACTIVE'>('ALL');

  const categories = Array.from(new Set(products.map((p) => p.category).filter(Boolean))) as string[];

  const filteredProducts = products.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.sku.toLowerCase().includes(search.toLowerCase()) ||
      (p.brand && p.brand.toLowerCase().includes(search.toLowerCase()));

    const matchesCategory = selectedCategory === 'ALL' || p.category === selectedCategory;

    const matchesStatus =
      statusFilter === 'ALL' ||
      (statusFilter === 'ACTIVE' && p.is_active) ||
      (statusFilter === 'INACTIVE' && !p.is_active);

    return matchesSearch && matchesCategory && matchesStatus;
  });

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
              Global Product Catalogue
            </h2>
            <span className="px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-[10px] font-bold uppercase tracking-wider border border-purple-500/30">
              Admin Price Authority
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            {selectedStore
              ? `Displaying catalogue inventory scoped to ${selectedStore.name}`
              : 'Global network catalogue with central pricing & Cloudinary photography'}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={onRefresh}
            className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-white transition"
            title="Refresh catalogue"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={onOpenAddModal}
            className="px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>Add New Product</span>
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
        <div className="sm:col-span-6 relative">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by product name, SKU, or brand..."
            className="w-full pl-10 pr-4 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
        </div>

        <div className="sm:col-span-3">
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="w-full py-2.5 px-3 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-300 focus:outline-none focus:border-purple-500"
          >
            <option value="ALL">All Categories ({products.length})</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'ALL' | 'ACTIVE' | 'INACTIVE')}
            className="w-full py-2.5 px-3 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-300 focus:outline-none focus:border-purple-500"
          >
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">Active (Storefront Visible)</option>
            <option value="INACTIVE">Deactivated Only</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="bg-slate-900/80 rounded-3xl border border-slate-800/80 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-900/90 border-b border-slate-800 text-[11px] uppercase font-bold text-slate-400 tracking-wider">
              <tr>
                <th className="p-4">Product Details</th>
                <th className="p-4">Category & Brand</th>
                <th className="p-4">Base Price</th>
                <th className="p-4">Inventory Status</th>
                <th className="p-4">State</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {filteredProducts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-12 text-center text-slate-500">
                    <Package className="w-8 h-8 mx-auto mb-2 opacity-30 text-slate-400" />
                    <p className="font-semibold text-slate-400">No matching products found</p>
                    <p className="text-[11px] text-slate-500 mt-1">
                      Try adjusting search filters or add a new catalogue product.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredProducts.map((p) => {
                  const img =
                    p.image?.secure_url ||
                    p.image?.url ||
                    (p.attributes?.image as { secure_url?: string })?.secure_url ||
                    getProductImage(p.sku, p.category);

                  const hasCloudinary = Boolean(p.image?.public_id || (p.attributes?.image as { public_id?: string })?.public_id);

                  return (
                    <tr key={p.id} className="hover:bg-slate-800/40 transition">
                      {/* Product Details */}
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="relative group shrink-0">
                            <img
                              src={img}
                              alt={p.name}
                              className="w-12 h-12 rounded-xl object-cover bg-slate-800 border border-slate-700"
                            />
                            {hasCloudinary && (
                              <span
                                className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-purple-500 border-2 border-slate-900"
                                title="Cloudinary CDN Hosted"
                              />
                            )}
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-white text-sm truncate max-w-xs">{p.name}</p>
                            <p className="text-[11px] text-slate-400 font-mono">
                              SKU: {p.sku}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Category & Brand */}
                      <td className="p-4">
                        <span className="inline-block px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 font-semibold text-[11px]">
                          {p.category || 'General'}
                        </span>
                        {p.brand && (
                          <p className="text-[11px] text-slate-400 mt-0.5">{p.brand}</p>
                        )}
                      </td>

                      {/* Price (in ₹) */}
                      <td className="p-4">
                        <span className="font-extrabold text-white text-sm">
                          {formatPrice(p.price_paise)}
                        </span>
                        <span className="text-[10px] text-purple-400 block font-semibold">
                          Editable by Admin
                        </span>
                      </td>

                      {/* Inventory */}
                      <td className="p-4">
                        {p.qty_on_hand !== undefined && p.qty_on_hand !== null ? (
                          <div>
                            <div className="flex items-center gap-1.5 font-semibold text-slate-200">
                              <span className="text-emerald-400">{p.qty_available ?? p.qty_on_hand} avail</span>
                              <span>/</span>
                              <span>{p.qty_on_hand} hand</span>
                            </div>
                            {(p.qty_reserved || 0) > 0 && (
                              <p className="text-[10px] text-amber-400 font-mono">
                                {p.qty_reserved} in 10-min hold
                              </p>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-500 text-[11px]">Global Catalogue</span>
                        )}
                      </td>

                      {/* Active Status */}
                      <td className="p-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                            p.is_active
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                              : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          }`}
                        >
                          {p.is_active ? 'Active' : 'Deactivated'}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button"
                            onClick={() => onOpenImageModal(p)}
                            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
                            title="Manage Cloudinary Photo"
                          >
                            <Camera className="w-4 h-4 text-purple-400" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onOpenEditModal(p)}
                            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"
                            title="Edit Details & Price"
                          >
                            <Edit2 className="w-4 h-4 text-indigo-400" />
                          </button>
                          {p.is_active && (
                            <button
                              type="button"
                              onClick={() => onDeactivateProduct(p)}
                              className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 transition"
                              title="Deactivate Product"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
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
