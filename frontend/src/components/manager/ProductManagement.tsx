import React, { useState, useMemo } from 'react';
import {
  Search,
  Plus,
  Edit2,
  Image as ImageIcon,
  Trash2,
  X,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import type { ManagerProduct } from '../../types';
import { formatPrice, getProductImage } from '../../utils/format';

interface ProductManagementProps {
  products: ManagerProduct[];
  onOpenAddModal: () => void;
  onOpenEditModal: (product: ManagerProduct) => void;
  onOpenImageModal: (product: ManagerProduct) => void;
  onDeactivateProduct: (product: ManagerProduct) => void;
  onRefresh: () => void;
  isAdmin: boolean;
}

const ITEMS_PER_PAGE = 10;

export const ProductManagement: React.FC<ProductManagementProps> = ({
  products,
  onOpenAddModal,
  onOpenEditModal,
  onOpenImageModal,
  onDeactivateProduct,
}) => {
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'INACTIVE'>('ALL');
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Extract categories for filter dropdown
  const categories = useMemo(() => {
    const set = new Set<string>();
    products.forEach((p) => {
      if (p.category) set.add(p.category);
    });
    return Array.from(set).sort();
  }, [products]);

  // Filtered and searched product list
  const filteredProducts = useMemo(() => {
    return products.filter((p) => {
      const q = searchTerm.toLowerCase().trim();
      const matchesSearch =
        !q ||
        p.name.toLowerCase().includes(q) ||
        p.sku.toLowerCase().includes(q) ||
        (p.brand && p.brand.toLowerCase().includes(q));

      const matchesCategory =
        selectedCategory === 'ALL' || p.category === selectedCategory;

      const matchesStatus =
        statusFilter === 'ALL' ||
        (statusFilter === 'ACTIVE' && p.is_active) ||
        (statusFilter === 'INACTIVE' && !p.is_active);

      return matchesSearch && matchesCategory && matchesStatus;
    });
  }, [products, searchTerm, selectedCategory, statusFilter]);

  // Pagination slice
  const totalPages = Math.max(1, Math.ceil(filteredProducts.length / ITEMS_PER_PAGE));
  const paginatedProducts = useMemo(() => {
    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredProducts.slice(start, start + ITEMS_PER_PAGE);
  }, [filteredProducts, currentPage]);

  const handleSearchChange = (val: string) => {
    setSearchTerm(val);
    setCurrentPage(1);
  };

  return (
    <div className="space-y-4">
      {/* 1. Header Toolbar */}
      <div className="p-4 sm:p-5 rounded-2xl bg-white border border-gray-200/90 shadow-xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        {/* Search Bar */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search products by SKU, name, or brand..."
            className="w-full pl-9 pr-8 py-2 text-xs sm:text-sm border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-gray-50/50"
          />
          {searchTerm && (
            <button
              onClick={() => handleSearchChange('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Filters and Add Action */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Category Filter */}
          <select
            value={selectedCategory}
            onChange={(e) => {
              setSelectedCategory(e.target.value);
              setCurrentPage(1);
            }}
            className="px-3 py-2 text-xs font-semibold border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
          >
            <option value="ALL">All Categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as 'ALL' | 'ACTIVE' | 'INACTIVE');
              setCurrentPage(1);
            }}
            className="px-3 py-2 text-xs font-semibold border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
          >
            <option value="ALL">All Status</option>
            <option value="ACTIVE">Active Only</option>
            <option value="INACTIVE">Deactivated</option>
          </select>

          {/* New Product Button */}
          <button
            type="button"
            onClick={onOpenAddModal}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-xs transition flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            <span>Add Product</span>
          </button>
        </div>
      </div>

      {/* 2. Product Table */}
      <div className="bg-white rounded-2xl border border-gray-200/90 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50/70 text-gray-500 font-semibold uppercase text-[11px] tracking-wider">
                <th className="py-3 px-4">Product & SKU</th>
                <th className="py-3 px-4">Brand / Category</th>
                <th className="py-3 px-4">Price</th>
                <th className="py-3 px-4 text-center">On-Hand</th>
                <th className="py-3 px-4 text-center">Reserved</th>
                <th className="py-3 px-4 text-center">Available</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {paginatedProducts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-gray-400">
                    <p className="font-semibold text-gray-700">No matching products found</p>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      Try adjusting your search criteria or category filter.
                    </p>
                  </td>
                </tr>
              ) : (
                paginatedProducts.map((p) => {
                  const img = p.image?.secure_url || p.image?.url || getProductImage(p.sku, p.category);
                  const onHand = p.qty_on_hand ?? 0;
                  const reserved = p.qty_reserved ?? 0;
                  const available = p.qty_available ?? 0;

                  return (
                    <tr key={p.id} className="hover:bg-gray-50/80 transition group">
                      {/* Product Thumbnail & Name */}
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <div className="relative w-10 h-10 rounded-lg bg-gray-50 border border-gray-200 overflow-hidden shrink-0">
                            <img src={img} alt={p.name} className="w-full h-full object-cover" />
                            {p.image?.secure_url && (
                              <span
                                className="absolute bottom-0 right-0 p-0.5 bg-emerald-600 text-white rounded-tl"
                                title="Cloudinary photography linked"
                              >
                                <Sparkles className="w-2.5 h-2.5" />
                              </span>
                            )}
                          </div>
                          <div className="min-w-0 max-w-xs">
                            <p className="font-bold text-gray-900 truncate text-xs sm:text-sm">
                              {p.name}
                            </p>
                            <p className="font-mono text-[11px] text-gray-400">{p.sku}</p>
                          </div>
                        </div>
                      </td>

                      {/* Brand & Category */}
                      <td className="py-3 px-4">
                        <span className="font-semibold text-gray-800 block">
                          {p.brand || 'Unbranded'}
                        </span>
                        <span className="text-[11px] text-gray-500">{p.category || 'General'}</span>
                      </td>

                      {/* Price in INR */}
                      <td className="py-3 px-4 font-bold text-gray-900">
                        {formatPrice(p.price_paise)}
                      </td>

                      {/* Stock Balances */}
                      <td className="py-3 px-4 text-center font-semibold text-gray-800">
                        {onHand}
                      </td>
                      <td className="py-3 px-4 text-center font-semibold text-amber-700">
                        {reserved}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span
                          className={`font-bold px-2 py-0.5 rounded-full text-[11px] ${
                            available <= 0
                              ? 'bg-red-100 text-red-800'
                              : available <= (p.low_stock_threshold || 5)
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {available}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            p.is_active
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-gray-100 text-gray-500 border border-gray-200'
                          }`}
                        >
                          {p.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => onOpenImageModal(p)}
                            className="p-1.5 rounded-lg text-gray-500 hover:text-emerald-700 hover:bg-emerald-50 transition"
                            title="Manage Cloudinary Photography"
                          >
                            <ImageIcon className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onOpenEditModal(p)}
                            className="p-1.5 rounded-lg text-gray-500 hover:text-blue-700 hover:bg-blue-50 transition"
                            title="Edit Product Details"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          {p.is_active && (
                            <button
                              type="button"
                              onClick={() => onDeactivateProduct(p)}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-red-700 hover:bg-red-50 transition"
                              title="Safe Deactivation (Soft Delete)"
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

        {/* 3. Pagination Footer */}
        {filteredProducts.length > ITEMS_PER_PAGE && (
          <div className="p-4 border-t border-gray-100 bg-gray-50/50 flex items-center justify-between text-xs text-gray-500">
            <span>
              Showing {(currentPage - 1) * ITEMS_PER_PAGE + 1} to{' '}
              {Math.min(currentPage * ITEMS_PER_PAGE, filteredProducts.length)} of{' '}
              {filteredProducts.length} items
            </span>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1.5 rounded-lg border border-gray-200 hover:bg-white disabled:opacity-40 transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-2 font-semibold text-gray-800">
                Page {currentPage} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1.5 rounded-lg border border-gray-200 hover:bg-white disabled:opacity-40 transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
