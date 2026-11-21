import React from 'react';
import {
  X,
  Trash2,
  Plus,
  Minus,
  ShoppingBag,
  Clock,
  ShieldCheck,
  ArrowRight,
  Store,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { useCart } from '../context/useCart';
import { formatPrice, getProductImage } from '../utils/format';

interface CartDrawerProps {
  currentStoreName?: string;
}

export const CartDrawer: React.FC<CartDrawerProps> = ({ currentStoreName }) => {
  const {
    items,
    totalItems,
    totalPaise,
    isCartOpen,
    setIsCartOpen,
    setIsCheckoutOpen,
    updateQuantity,
    removeItem,
    clearAllItems,
    isMutating,
    reservationTimer,
    expiryAlert,
    dismissExpiryAlert,
    cartError,
    clearCartError,
  } = useCart();

  if (!isCartOpen) return null;

  const handleCheckoutClick = () => {
    setIsCartOpen(false);
    setIsCheckoutOpen(true);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-xs transition-opacity animate-fade-in"
        onClick={() => setIsCartOpen(false)}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white shadow-2xl flex flex-col">
          {/* Header */}
          <div className="p-4 sm:p-5 border-b border-gray-100 flex items-center justify-between bg-gray-50/70">
            <div className="flex items-center gap-2">
              <ShoppingBag className="w-5 h-5 text-emerald-600" />
              <h2 className="font-bold text-gray-900 text-lg">Your Cart</h2>
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                {totalItems} {totalItems === 1 ? 'item' : 'items'}
              </span>
            </div>
            <button
              onClick={() => setIsCartOpen(false)}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-200/60 transition-colors"
              aria-label="Close cart"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Fulfillment Store Tag */}
          {currentStoreName && (
            <div className="px-5 py-2 bg-emerald-50/60 border-b border-emerald-100 flex items-center justify-between text-xs text-emerald-800">
              <div className="flex items-center gap-1.5 font-medium truncate">
                <Store className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
                <span className="truncate">Store: {currentStoreName}</span>
              </div>
              <span className="text-[11px] text-emerald-600 shrink-0 font-semibold uppercase tracking-wider">
                Hyperlocal
              </span>
            </div>
          )}

          {/* Stock Reservation 10-Minute Countdown Banner */}
          {reservationTimer && items.length > 0 && !reservationTimer.isExpired && (
            <div
              className={`px-4 py-2.5 border-b text-xs flex items-center justify-between transition-colors ${
                reservationTimer.isUrgent
                  ? 'bg-red-50 border-red-200 text-red-800 animate-pulse'
                  : reservationTimer.isWarning
                  ? 'bg-amber-50 border-amber-200 text-amber-800'
                  : 'bg-emerald-50/90 border-emerald-200 text-emerald-900'
              }`}
            >
              <div className="flex items-center gap-2 font-medium">
                <Clock
                  className={`w-4 h-4 shrink-0 ${
                    reservationTimer.isUrgent
                      ? 'text-red-600'
                      : reservationTimer.isWarning
                      ? 'text-amber-600'
                      : 'text-emerald-600'
                  }`}
                />
                <span>
                  {reservationTimer.isUrgent
                    ? 'Reservation expiring soon!'
                    : reservationTimer.isWarning
                    ? 'Stock hold expiring soon:'
                    : 'Stock Reserved in PostgreSQL:'}
                </span>
              </div>
              <span
                className={`font-mono font-bold px-2 py-0.5 rounded ${
                  reservationTimer.isUrgent
                    ? 'bg-red-600 text-white'
                    : reservationTimer.isWarning
                    ? 'bg-amber-500 text-white'
                    : 'bg-emerald-600 text-white'
                }`}
              >
                {reservationTimer.formattedTime}
              </span>
            </div>
          )}

          {/* Expiry Alert Notice */}
          {expiryAlert && (
            <div className="m-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800 flex items-start justify-between gap-2 animate-fade-in">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-amber-900">Hold Expired</p>
                  <p className="text-[11px] text-amber-700 mt-0.5">{expiryAlert}</p>
                </div>
              </div>
              <button
                onClick={dismissExpiryAlert}
                className="text-amber-500 hover:text-amber-700 p-0.5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Cart Error Notice */}
          {cartError && (
            <div className="m-4 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-800 flex items-start justify-between gap-2 animate-fade-in">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                <p>{cartError}</p>
              </div>
              <button
                onClick={clearCartError}
                className="text-red-500 hover:text-red-700 p-0.5"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Line Items List */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
            {items.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-6 text-gray-500">
                <div className="w-16 h-16 rounded-2xl bg-gray-100 flex items-center justify-center mb-4 text-gray-400">
                  <ShoppingBag className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold text-gray-900 mb-1">Your cart is empty</h3>
                <p className="text-xs text-gray-500 max-w-xs mb-6">
                  Add items from the catalog. Each item is atomically locked for 10 minutes so nobody else can take it.
                </p>
                <button
                  onClick={() => setIsCartOpen(false)}
                  className="px-5 py-2.5 rounded-xl bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 transition-colors shadow-sm"
                >
                  Start Shopping
                </button>
              </div>
            ) : (
              items.map((item) => {
                const img = getProductImage(item.product_sku);
                return (
                  <div
                    key={item.reservation_id}
                    className="flex gap-3 p-3 rounded-xl border border-gray-100 bg-white hover:border-gray-200 transition-colors shadow-xs"
                  >
                    <img
                      src={img}
                      alt={item.product_name}
                      className="w-16 h-16 rounded-lg object-cover bg-gray-50 shrink-0 border border-gray-100"
                    />
                    <div className="flex-1 min-w-0 flex flex-col justify-between">
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="text-xs font-semibold text-gray-900 truncate">
                            {item.product_name}
                          </h4>
                          <button
                            onClick={() => removeItem(item.product_id)}
                            disabled={isMutating}
                            className="text-gray-400 hover:text-red-600 p-1 transition-colors disabled:opacity-50"
                            aria-label="Remove item"
                            title="Release stock hold"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[11px] text-gray-400 font-mono">
                            SKU: {item.product_sku}
                          </span>
                          <span className="text-[11px] font-semibold text-emerald-700">
                            {formatPrice(item.unit_price_paise)}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-50">
                        {/* Quantity Stepper */}
                        <div className="flex items-center border border-gray-200 rounded-lg bg-gray-50">
                          <button
                            type="button"
                            onClick={() => updateQuantity(item.product_id, item.qty - 1)}
                            disabled={isMutating}
                            className="p-1 hover:bg-white text-gray-600 disabled:opacity-40 transition-colors rounded-l-md"
                            aria-label="Decrease quantity"
                          >
                            <Minus className="w-3 h-3" />
                          </button>
                          <span className="px-2 text-xs font-semibold text-gray-800 min-w-6 text-center">
                            {item.qty}
                          </span>
                          <button
                            type="button"
                            onClick={() => updateQuantity(item.product_id, item.qty + 1)}
                            disabled={isMutating}
                            className="p-1 hover:bg-white text-gray-600 disabled:opacity-40 transition-colors rounded-r-md"
                            aria-label="Increase quantity"
                          >
                            <Plus className="w-3 h-3" />
                          </button>
                        </div>

                        {/* Item Subtotal */}
                        <div className="text-right">
                          <span className="text-xs font-bold text-gray-900">
                            {formatPrice(item.item_subtotal_paise)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer & Checkout Action */}
          {items.length > 0 && (
            <div className="p-4 sm:p-5 border-t border-gray-100 bg-gray-50/70 space-y-3">
              <div className="space-y-1.5 text-xs text-gray-600">
                <div className="flex justify-between">
                  <span>Subtotal ({totalItems} items)</span>
                  <span className="font-medium text-gray-900">{formatPrice(totalPaise)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Hyperlocal Delivery</span>
                  <span className="text-emerald-700 font-medium">FREE</span>
                </div>
                <div className="pt-2 border-t border-gray-200 flex justify-between text-sm font-bold text-gray-900">
                  <span>Total Amount</span>
                  <span className="text-base text-emerald-700">{formatPrice(totalPaise)}</span>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1 text-[11px] text-gray-500">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span>Zero Overselling Guarantee: Stock held in PostgreSQL</span>
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={clearAllItems}
                  disabled={isMutating}
                  className="px-3 py-2.5 rounded-xl border border-gray-200 text-gray-600 hover:bg-gray-100 text-xs font-semibold transition-colors disabled:opacity-50"
                  title="Release all reservations"
                >
                  Clear
                </button>

                <button
                  type="button"
                  onClick={handleCheckoutClick}
                  disabled={isMutating || (reservationTimer?.isExpired ?? false)}
                  className="flex-1 py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs sm:text-sm font-semibold flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
                >
                  {isMutating ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <span>Proceed to Checkout</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
