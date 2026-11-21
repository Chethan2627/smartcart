import React, { useState } from 'react';
import {
  X,
  MapPin,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Store,
  ArrowLeft,
  Loader2,
  PackageCheck,
  Zap,
} from 'lucide-react';
import { useCart } from '../context/useCart';
import { useAuth } from '../context/useAuth';
import { submitCheckout } from '../api/client';
import type { OrderResponse } from '../types';
import { formatPrice, getProductImage } from '../utils/format';

interface CheckoutModalProps {
  currentStoreName?: string;
  onOrderSuccess?: () => void;
}

export const CheckoutModal: React.FC<CheckoutModalProps> = ({
  currentStoreName,
  onOrderSuccess,
}) => {
  const { isCheckoutOpen, setIsCheckoutOpen, cart, items, totalItems, totalPaise, reservationTimer, refreshCart } = useCart();
  const { user, customerProfile } = useAuth();

  const [addressOverride, setAddressOverride] = useState<string | null>(null);
  const deliveryAddress = addressOverride !== null ? addressOverride : (customerProfile?.address || '');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmedOrder, setConfirmedOrder] = useState<OrderResponse | null>(null);

  // Generate a cryptographically random Idempotency-Key per checkout attempt
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => {
    const uuid = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `key_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    return `checkout_${uuid}`.replace(/[^A-Za-z0-9_-]/g, '');
  });

  if (!isCheckoutOpen) return null;

  const handleClose = () => {
    if (isSubmitting) return; // Prevent closing mid-transaction
    setIsCheckoutOpen(false);
    setConfirmedOrder(null);
    setError(null);
    setAddressOverride(null);
  };

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cart?.store_id) {
      setError('Cannot determine fulfillment store for this cart.');
      return;
    }
    if (reservationTimer?.isExpired) {
      setError('Your 10-minute stock reservation has expired. Please return to the cart to re-reserve available items.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const order = await submitCheckout(
        {
          store_id: cart.store_id,
          delivery_address: deliveryAddress.trim() || undefined,
        },
        idempotencyKey
      );

      setConfirmedOrder(order);
      // Refresh cart state from backend (which will now be empty since reservations were converted)
      await refreshCart();
      if (onOrderSuccess) {
        onOrderSuccess();
      }
    } catch (err: unknown) {
      console.error('Checkout failed:', err);
      setError(err instanceof Error ? err.message : 'Checkout transaction failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDoneShopping = () => {
    setConfirmedOrder(null);
    setIsCheckoutOpen(false);
    setAddressOverride(null);
    // Regenerate idempotency key for next checkout
    const uuid = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `key_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    setIdempotencyKey(`checkout_${uuid}`.replace(/[^A-Za-z0-9_-]/g, ''));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/60 backdrop-blur-sm overflow-y-auto animate-fade-in">
      <div
        className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ========================================================= */}
        {/* VIEW 1: ORDER CONFIRMATION VIEW                          */}
        {/* ========================================================= */}
        {confirmedOrder ? (
          <div className="p-6 sm:p-8 text-center animate-fade-in">
            <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 className="w-10 h-10" />
            </div>

            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 uppercase tracking-wider">
              Order {confirmedOrder.status}
            </span>

            <h2 className="text-2xl font-bold text-gray-900 mt-2">
              Thank You for Your Order!
            </h2>
            <p className="text-sm text-gray-500 mt-1">
              Your hyper-local grocery order has been locked and confirmed.
            </p>

            <div className="mt-6 p-4 rounded-xl bg-gray-50 border border-gray-100 text-left space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-gray-200">
                <div>
                  <span className="text-xs text-gray-500 block">Order Number</span>
                  <span className="text-base font-mono font-bold text-emerald-700">
                    {confirmedOrder.order_number}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xs text-gray-500 block">Total Paid</span>
                  <span className="text-base font-bold text-gray-900">
                    {formatPrice(confirmedOrder.total_paise)}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-gray-600">
                <div>
                  <span className="text-gray-400 block">Fulfillment Store:</span>
                  <span className="font-semibold text-gray-800">
                    {currentStoreName || 'Local Fulfillment Store'}
                  </span>
                </div>
                <div>
                  <span className="text-gray-400 block">Delivery Address:</span>
                  <span className="font-semibold text-gray-800">
                    {deliveryAddress.trim() || customerProfile?.address || 'Self Pick-up at Counter'}
                  </span>
                </div>
              </div>

              {/* Kafka & Transactional Outbox indicator */}
              <div className="p-2.5 rounded-lg bg-emerald-50/80 border border-emerald-100 flex items-center gap-2 text-[11px] text-emerald-800">
                <Zap className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>
                  <strong>Transactional Outbox:</strong> Event emitted to Aiven Kafka cluster topic{' '}
                  <code className="font-mono font-semibold">smartcart.orders</code> for live fulfillment dispatch.
                </span>
              </div>
            </div>

            <div className="mt-6">
              <button
                type="button"
                onClick={handleDoneShopping}
                className="w-full sm:w-auto px-8 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm transition-colors shadow-sm"
              >
                Continue Shopping
              </button>
            </div>
          </div>
        ) : (
          /* ========================================================= */
          /* VIEW 2: CHECKOUT REVIEW & SUBMIT FORM                    */
          /* ========================================================= */
          <div>
            {/* Header */}
            <div className="p-4 sm:p-5 border-b border-gray-100 bg-gray-50/70 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleClose}
                  className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-200/60 transition-colors mr-1"
                  aria-label="Back to cart"
                >
                  <ArrowLeft className="w-5 h-5" />
                </button>
                <div>
                  <h2 className="font-bold text-gray-900 text-lg">Checkout</h2>
                  <p className="text-xs text-gray-500">Atomic reservation to confirmed order</p>
                </div>
              </div>

              <button
                type="button"
                onClick={handleClose}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 10-Minute Hold Status Banner */}
            {reservationTimer && !reservationTimer.isExpired && (
              <div
                className={`px-4 py-2 border-b text-xs flex items-center justify-between ${
                  reservationTimer.isUrgent
                    ? 'bg-red-50 border-red-200 text-red-800 animate-pulse'
                    : reservationTimer.isWarning
                    ? 'bg-amber-50 border-amber-200 text-amber-800'
                    : 'bg-emerald-50/80 border-emerald-200 text-emerald-900'
                }`}
              >
                <div className="flex items-center gap-2 font-medium">
                  <Clock className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Reserved Stock Hold Time Remaining:</span>
                </div>
                <span className="font-mono font-bold px-2 py-0.5 rounded bg-emerald-600 text-white">
                  {reservationTimer.formattedTime}
                </span>
              </div>
            )}

            <form onSubmit={handlePlaceOrder} className="p-5 sm:p-6 space-y-5">
              {error && (
                <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Checkout Error</span>
                    <span>{error}</span>
                  </div>
                </div>
              )}

              {/* 1. Fulfillment Location */}
              <div className="p-3.5 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
                    <Store className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-[11px] text-gray-500 block uppercase tracking-wider font-semibold">
                      Fulfillment Store
                    </span>
                    <span className="text-xs sm:text-sm font-semibold text-gray-900">
                      {currentStoreName || 'Selected Fulfillment Store'}
                    </span>
                  </div>
                </div>
                <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-100/60 px-2 py-0.5 rounded-full">
                  15-Min Express
                </span>
              </div>

              {/* 2. Customer Contact & Delivery Details */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Delivery Address</span>
                </h3>

                <div className="p-3 rounded-xl bg-gray-50/60 border border-gray-200 space-y-2">
                  <div className="flex flex-wrap items-center justify-between text-xs text-gray-600 gap-1 pb-2 border-b border-gray-100">
                    <span>
                      Customer: <strong>{user?.full_name || 'Valued Customer'}</strong>
                    </span>
                    <span>{customerProfile?.phone ? `Phone: ${customerProfile.phone}` : user?.email}</span>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-gray-600 mb-1">
                      Street Address & Landmark (or pickup note)
                    </label>
                    <textarea
                      rows={2}
                      value={deliveryAddress}
                      onChange={(e) => setAddressOverride(e.target.value)}
                      placeholder="e.g. 123 MG Road, Koramangala 4th Block, Bengaluru"
                      className="w-full p-2.5 text-xs sm:text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
                    />
                  </div>
                </div>
              </div>

              {/* 3. Order Items Summary */}
              <div>
                <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <PackageCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Order Items ({totalItems})</span>
                </h3>

                <div className="max-h-48 overflow-y-auto rounded-xl border border-gray-100 divide-y divide-gray-100 bg-gray-50/30">
                  {items.map((item) => (
                    <div key={item.reservation_id} className="p-2.5 flex items-center justify-between gap-3 text-xs">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <img
                          src={getProductImage(item.product_sku)}
                          alt={item.product_name}
                          className="w-9 h-9 rounded-md object-cover bg-white border border-gray-200 shrink-0"
                        />
                        <div className="truncate">
                          <p className="font-semibold text-gray-900 truncate">{item.product_name}</p>
                          <p className="text-[11px] text-gray-500">
                            Qty: {item.qty} × {formatPrice(item.unit_price_paise)}
                          </p>
                        </div>
                      </div>
                      <span className="font-bold text-gray-900 shrink-0">
                        {formatPrice(item.item_subtotal_paise)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* 4. Total & Idempotency Key Info */}
              <div className="pt-3 border-t border-gray-200 space-y-1.5 text-xs">
                <div className="flex justify-between text-gray-600">
                  <span>Subtotal</span>
                  <span>{formatPrice(totalPaise)}</span>
                </div>
                <div className="flex justify-between text-gray-600">
                  <span>Delivery Charges</span>
                  <span className="text-emerald-700 font-semibold">FREE</span>
                </div>
                <div className="flex justify-between text-base font-bold text-gray-900 pt-1">
                  <span>Total Amount</span>
                  <span className="text-emerald-700">{formatPrice(totalPaise)}</span>
                </div>
                <div className="pt-2 text-[10px] text-gray-400 font-mono truncate">
                  Idempotency-Key: {idempotencyKey}
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting || items.length === 0 || (reservationTimer?.isExpired ?? false)}
                className="w-full py-3.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>Confirming Order with Database Lock...</span>
                  </>
                ) : (
                  <span>Place Order • {formatPrice(totalPaise)}</span>
                )}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
