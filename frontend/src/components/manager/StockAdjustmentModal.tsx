import React, { useState } from 'react';
import { X, ArrowUpDown, PlusCircle, MinusCircle, CheckCircle, AlertCircle, Loader2, ShieldAlert } from 'lucide-react';
import type { ManagerProduct, StockAdjustmentType } from '../../types';
import { adjustProductStock } from '../../api/client';

interface StockAdjustmentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  product: ManagerProduct | null;
  storeId?: string;
}

export const StockAdjustmentModal: React.FC<StockAdjustmentModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  product,
  storeId,
}) => {
  const [adjType, setAdjType] = useState<StockAdjustmentType>('INCREASE');
  const [quantity, setQuantity] = useState<number>(10);
  const [reason, setReason] = useState<string>('Stock received from vendor delivery');
  const [newThreshold, setNewThreshold] = useState<string>(() =>
    product?.low_stock_threshold !== undefined && product.low_stock_threshold !== null
      ? String(product.low_stock_threshold)
      : '5'
  );

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !product) return null;

  const currentOnHand = product.qty_on_hand || 0;
  const currentReserved = product.qty_reserved || 0;
  const currentAvailable = product.qty_available || 0;

  // Compute live projected inventory balances
  let projectedOnHand = currentOnHand;
  if (adjType === 'INCREASE') {
    projectedOnHand = currentOnHand + quantity;
  } else if (adjType === 'DECREASE') {
    projectedOnHand = Math.max(0, currentOnHand - quantity);
  } else if (adjType === 'SET') {
    projectedOnHand = Math.max(0, quantity);
  }
  const projectedAvailable = Math.max(0, projectedOnHand - currentReserved);
  const isInvalidDecrease = adjType === 'DECREASE' && currentOnHand - quantity < currentReserved;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (quantity < 0) {
      setError('Quantity must be a non-negative integer.');
      return;
    }

    if (!reason.trim() || reason.trim().length < 3) {
      setError('A mandatory business justification reason (minimum 3 characters) is required for audit logging.');
      return;
    }

    if (isInvalidDecrease) {
      setError(
        `Cannot reduce stock below active reservations (${currentReserved} units currently held by customers).`
      );
      return;
    }

    setSubmitting(true);
    try {
      const thresholdVal = newThreshold.trim() ? parseInt(newThreshold, 10) : undefined;
      await adjustProductStock(
        product.id,
        {
          adjustment_type: adjType,
          quantity,
          reason: reason.trim(),
          low_stock_threshold: !isNaN(thresholdVal!) ? thresholdVal : undefined,
        },
        storeId
      );

      onSuccess();
      onClose();
    } catch (err: unknown) {
      console.error('Stock adjustment error:', err);
      setError(err instanceof Error ? err.message : 'Failed to perform stock adjustment.');
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
              <ArrowUpDown className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">Adjust Store Stock</h3>
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

        <form onSubmit={handleSubmit} className="p-5 sm:p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Current vs Projected Balance Cards */}
          <div className="grid grid-cols-3 gap-2 p-3 bg-gray-50 rounded-xl border border-gray-200 text-center">
            <div className="p-2 bg-white rounded-lg border border-gray-100 shadow-xs">
              <span className="text-[10px] text-gray-400 block font-semibold uppercase">Physical On-Hand</span>
              <span className="text-base font-bold text-gray-900">{currentOnHand}</span>
              <span className="text-[10px] text-emerald-600 font-bold block mt-0.5">
                → {projectedOnHand}
              </span>
            </div>
            <div className="p-2 bg-white rounded-lg border border-gray-100 shadow-xs">
              <span className="text-[10px] text-gray-400 block font-semibold uppercase">Reserved Holds</span>
              <span className="text-base font-bold text-amber-600">{currentReserved}</span>
              <span className="text-[10px] text-gray-400 block mt-0.5">Protected Lock</span>
            </div>
            <div className="p-2 bg-white rounded-lg border border-gray-100 shadow-xs">
              <span className="text-[10px] text-gray-400 block font-semibold uppercase">Available</span>
              <span className="text-base font-bold text-emerald-700">{currentAvailable}</span>
              <span className="text-[10px] text-emerald-600 font-bold block mt-0.5">
                → {projectedAvailable}
              </span>
            </div>
          </div>

          {/* Adjustment Mode Selector */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
              Adjustment Type *
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setAdjType('INCREASE')}
                className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  adjType === 'INCREASE'
                    ? 'border-emerald-600 bg-emerald-50 text-emerald-800 ring-2 ring-emerald-500/20'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                <PlusCircle className="w-3.5 h-3.5 text-emerald-600" />
                <span>Receive (+)</span>
              </button>

              <button
                type="button"
                onClick={() => setAdjType('DECREASE')}
                className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  adjType === 'DECREASE'
                    ? 'border-amber-600 bg-amber-50 text-amber-800 ring-2 ring-amber-500/20'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                <MinusCircle className="w-3.5 h-3.5 text-amber-600" />
                <span>Reduce (-)</span>
              </button>

              <button
                type="button"
                onClick={() => setAdjType('SET')}
                className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  adjType === 'SET'
                    ? 'border-blue-600 bg-blue-50 text-blue-800 ring-2 ring-blue-500/20'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                <CheckCircle className="w-3.5 h-3.5 text-blue-600" />
                <span>Reconcile (=)</span>
              </button>
            </div>
          </div>

          {/* Quantity & Threshold */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                {adjType === 'SET' ? 'New On-Hand Count *' : 'Adjustment Units *'}
              </label>
              <input
                type="number"
                min="0"
                required
                value={quantity}
                onChange={(e) => setQuantity(Math.max(0, parseInt(e.target.value, 10) || 0))}
                className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Low-Stock Threshold
              </label>
              <input
                type="number"
                min="0"
                value={newThreshold}
                onChange={(e) => setNewThreshold(e.target.value)}
                placeholder="5"
                className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>
          </div>

          {/* Mandatory Business Justification */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">
              Business Justification / Reason * (Mandatory for PostgreSQL Audit Trigger)
            </label>
            <input
              type="text"
              required
              minLength={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Inward shipment PO-9482 from supplier"
              className="w-full px-3 py-2 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <span className="text-[10px] text-gray-400 mt-0.5 block flex items-center gap-1">
              <ShieldAlert className="w-3 h-3 text-emerald-600 shrink-0" />
              <span>Persisted to immutable PostgreSQL inventory_audit_log table.</span>
            </span>
          </div>

          {/* Buttons */}
          <div className="pt-3 border-t border-gray-100 flex items-center justify-end gap-3">
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
              disabled={submitting || isInvalidDecrease}
              className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-xs transition flex items-center gap-2 disabled:opacity-50"
            >
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Confirm Stock Adjustment</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
