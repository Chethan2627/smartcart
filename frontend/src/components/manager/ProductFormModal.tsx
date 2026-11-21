import React, { useState } from 'react';
import { X, Package, AlertCircle, Loader2 } from 'lucide-react';
import type { ManagerProduct, ProductCreateManagerPayload, ProductUpdateManagerPayload } from '../../types';
import { createManagerProduct, updateManagerProduct } from '../../api/client';

interface ProductFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  productToEdit?: ManagerProduct | null;
  storeId?: string;
  isAdmin?: boolean;
}

const CANONICAL_CATEGORIES = [
  'Grocery',
  'Electronics',
  'Mobiles',
  'Dairy & Breakfast',
  'Pantry Essentials',
  'Beverages',
  'Bakery & Snacks',
  'Organic Staples',
];

export const ProductFormModal: React.FC<ProductFormModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  productToEdit,
  storeId,
  isAdmin = false,
}) => {
  const isEditing = Boolean(productToEdit);

  const [sku, setSku] = useState(() => productToEdit?.sku || '');
  const [name, setName] = useState(() => productToEdit?.name || '');
  const [description, setDescription] = useState(() => productToEdit?.description || '');
  const [brand, setBrand] = useState(() => productToEdit?.brand || '');
  const [category, setCategory] = useState(() => productToEdit?.category || 'Grocery');
  const [priceRupees, setPriceRupees] = useState(() =>
    productToEdit ? (productToEdit.price_paise / 100).toFixed(2) : '99.00'
  );
  const [initialStock, setInitialStock] = useState<number>(20);
  const [lowStockThreshold, setLowStockThreshold] = useState<number>(5);
  const [isActive, setIsActive] = useState<boolean>(() => productToEdit?.is_active ?? true);

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Product display name is required.');
      return;
    }

    const priceNum = parseFloat(priceRupees);
    if (isNaN(priceNum) || priceNum < 0) {
      setError('Please provide a valid non-negative price in Rupees.');
      return;
    }
    const pricePaise = Math.round(priceNum * 100);

    setSubmitting(true);
    try {
      if (isEditing && productToEdit) {
        const updatePayload: ProductUpdateManagerPayload = {
          name: name.trim(),
          description: description.trim() || undefined,
          brand: brand.trim() || undefined,
          category: category.trim() || undefined,
          is_active: isActive,
        };
        // Only admins can alter price on existing products per backend rule
        if (isAdmin) {
          updatePayload.price_paise = pricePaise;
        }

        await updateManagerProduct(productToEdit.id, updatePayload, storeId);
      } else {
        if (!sku.trim()) {
          setError('SKU code is required (min 2 characters).');
          setSubmitting(false);
          return;
        }

        const createPayload: ProductCreateManagerPayload = {
          sku: sku.trim().toUpperCase(),
          name: name.trim(),
          description: description.trim() || undefined,
          brand: brand.trim() || undefined,
          category: category.trim() || undefined,
          price_paise: pricePaise,
          initial_stock: Math.max(0, initialStock),
          low_stock_threshold: Math.max(0, lowStockThreshold),
          attributes: {},
        };

        await createManagerProduct(createPayload, storeId);
      }

      onSuccess();
      onClose();
    } catch (err: unknown) {
      console.error('Save product error:', err);
      setError(err instanceof Error ? err.message : 'Failed to save product details.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/60 backdrop-blur-sm overflow-y-auto animate-fade-in">
      <div
        className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-gray-100 bg-gray-50/70 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <Package className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">
                {isEditing ? 'Edit Product Catalogue Item' : 'Add New Product to Catalogue'}
              </h3>
              <p className="text-xs text-gray-500">
                {isEditing ? `Modifying SKU: ${productToEdit?.sku}` : 'Initializes global product and store inventory'}
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

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4 max-h-[80vh] overflow-y-auto">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* SKU */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Product SKU *
              </label>
              <input
                type="text"
                required
                disabled={isEditing}
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder="e.g. MILK-1L"
                className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 uppercase disabled:bg-gray-100 disabled:text-gray-500"
              />
              <span className="text-[10px] text-gray-400 mt-0.5 block">
                {isEditing ? 'SKU cannot be altered after creation' : 'Unique barcode / inventory SKU'}
              </span>
            </div>

            {/* Price */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Price (INR ₹) *
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-gray-500">
                  ₹
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  disabled={isEditing && !isAdmin}
                  value={priceRupees}
                  onChange={(e) => setPriceRupees(e.target.value)}
                  placeholder="149.00"
                  className="w-full pl-7 pr-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:bg-gray-100 disabled:text-gray-500"
                />
              </div>
              <span className="text-[10px] text-gray-400 mt-0.5 block">
                {isEditing && !isAdmin ? 'Price updates require administrator privilege' : 'Global retail price'}
              </span>
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">
              Product Name *
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Organic Farm Fresh Milk 1L"
              className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Brand */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Brand
              </label>
              <input
                type="text"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
                placeholder="e.g. Nandini, Amul, boAt"
                className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            {/* Category */}
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
              >
                {CANONICAL_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">
              Description
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Product specifications, ingredients, storage tips..."
              className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* Create-only initial stock inputs */}
          {!isEditing ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-gray-100">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Initial Stock (On-Hand)
                </label>
                <input
                  type="number"
                  min="0"
                  value={initialStock}
                  onChange={(e) => setInitialStock(parseInt(e.target.value, 10) || 0)}
                  className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <span className="text-[10px] text-gray-400 mt-0.5 block">
                  Initial physical units for this store
                </span>
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Low-Stock Threshold
                </label>
                <input
                  type="number"
                  min="0"
                  value={lowStockThreshold}
                  onChange={(e) => setLowStockThreshold(parseInt(e.target.value, 10) || 0)}
                  className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <span className="text-[10px] text-gray-400 mt-0.5 block">
                  Triggers warning when stock drops to this level
                </span>
              </div>
            </div>
          ) : (
            /* Edit-only Active Status Toggle */
            <div className="pt-2 border-t border-gray-100 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-gray-800 block">Product Status</span>
                <span className="text-[11px] text-gray-500">
                  {isActive ? 'Active and discoverable in storefront' : 'Deactivated from customer view'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setIsActive(!isActive)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  isActive ? 'bg-emerald-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                    isActive ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          )}

          {/* Action Buttons */}
          <div className="pt-4 border-t border-gray-100 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="px-4 py-2 rounded-xl border border-gray-200 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-xs transition flex items-center gap-2 disabled:opacity-50"
            >
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{isEditing ? 'Save Changes' : 'Create Product'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
