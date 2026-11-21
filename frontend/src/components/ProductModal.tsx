import React from 'react';
import {
  X,
  Star,
  ShieldCheck,
  Zap,
  MapPin,
  Check,
  AlertTriangle,
  XCircle,
  Plus,
  Minus,
  ShoppingBag,
} from 'lucide-react';
import type { ProductSearchResultItem, Store } from '../types';
import {
  formatPrice,
  getOriginalPrice,
  getProductImage,
  getProductRating,
} from '../utils/format';

interface ProductModalProps {
  product: ProductSearchResultItem | null;
  store: Store | null;
  onClose: () => void;
  cartQuantity: number;
  onAddToCart: (product: ProductSearchResultItem) => void;
  onUpdateCartQuantity: (product: ProductSearchResultItem, quantity: number) => void;
}

export const ProductModal: React.FC<ProductModalProps> = ({
  product,
  store,
  onClose,
  cartQuantity,
  onAddToCart,
  onUpdateCartQuantity,
}) => {
  if (!product) return null;

  const { rating, reviews } = getProductRating(product.sku);
  const isInStock = product.is_in_stock && product.qty_available > 0;
  const isLowStock = isInStock && product.qty_available <= 5;
  const imageSrc = getProductImage(product.sku, product.category, product.image_url);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-950/70 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="relative w-full max-w-3xl bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-200 my-8">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 p-2 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-500 hover:text-slate-800 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="grid grid-cols-1 md:grid-cols-2">
          {/* Product Media */}
          <div className="relative aspect-square md:aspect-auto bg-slate-50 p-8 flex items-center justify-center border-b md:border-b-0 md:border-r border-slate-200">
            <img
              src={imageSrc}
              alt={product.name}
              className="w-full h-full max-h-96 object-contain rounded-2xl shadow-sm"
            />
            {/* Stock status overlay */}
            <div className="absolute bottom-4 left-4">
              {!isInStock ? (
                <span className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200">
                  <XCircle className="w-4 h-4 text-rose-600" />
                  <span>Out of Stock at this store</span>
                </span>
              ) : isLowStock ? (
                <span className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-amber-50 text-amber-800 border border-amber-200">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span>Only {product.qty_available} units remaining!</span>
                </span>
              ) : (
                <span className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                  <Check className="w-4 h-4 text-emerald-600" />
                  <span>Verified In Stock ({product.qty_available} units)</span>
                </span>
              )}
            </div>
          </div>

          {/* Product Content & Buy Actions */}
          <div className="p-6 sm:p-8 flex flex-col justify-between">
            <div>
              {/* Category, Brand, SKU */}
              <div className="flex items-center space-x-2 text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                {product.brand && <span className="text-indigo-600">{product.brand}</span>}
                {product.brand && <span>•</span>}
                <span>{product.category || 'General'}</span>
                <span>•</span>
                <span className="font-mono text-slate-400">{product.sku}</span>
              </div>

              {/* Title */}
              <h2 className="text-xl sm:text-2xl font-black text-slate-900 leading-snug">
                {product.name}
              </h2>

              {/* Rating */}
              <div className="flex items-center space-x-2 mt-2.5">
                <div className="flex items-center text-amber-500">
                  <Star className="w-4 h-4 fill-amber-400 text-amber-400" />
                </div>
                <span className="text-sm font-bold text-slate-800">{rating} out of 5</span>
                <span className="text-xs text-slate-400">({reviews} customer ratings)</span>
              </div>

              {/* Price Block */}
              <div className="mt-4 p-4 rounded-2xl bg-slate-50 border border-slate-200/80">
                <div className="flex items-baseline space-x-2">
                  <span className="text-2xl sm:text-3xl font-black text-slate-900">
                    {formatPrice(product.price_paise)}
                  </span>
                  <span className="text-sm text-slate-400 line-through">
                    {getOriginalPrice(product.price_paise)}
                  </span>
                  <span className="text-xs font-extrabold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-md">
                    20% OFF
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">Inclusive of all local taxes & GST</p>
              </div>

              {/* Description */}
              {product.description && (
                <div className="mt-4">
                  <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-1">
                    About this product
                  </h4>
                  <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
                    {product.description}
                  </p>
                </div>
              )}

              {/* Fulfillment Hub Info */}
              <div className="mt-4 p-3 rounded-xl bg-indigo-50/70 border border-indigo-100 flex items-start space-x-3 text-xs text-slate-700">
                <MapPin className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold text-slate-900">
                    Fulfilling from: {store?.name || 'Local Fulfillment Center'}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {store?.address ? `${store.address}, ` : ''}{store?.city || 'Bengaluru'}
                  </p>
                  <div className="flex items-center space-x-3 mt-1.5 text-indigo-700 font-semibold text-[11px]">
                    <span className="flex items-center space-x-1">
                      <Zap className="w-3.5 h-3.5 text-amber-500" />
                      <span>15-min Delivery</span>
                    </span>
                    <span className="flex items-center space-x-1">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                      <span>10-min Stock Hold</span>
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Add to Cart CTA */}
            <div className="mt-6 pt-4 border-t border-slate-200">
              {!isInStock ? (
                <button
                  disabled
                  className="w-full py-3 rounded-xl bg-slate-100 text-slate-400 font-bold text-sm cursor-not-allowed border border-slate-200 text-center"
                >
                  Currently Out of Stock at this store
                </button>
              ) : cartQuantity > 0 ? (
                <div className="flex items-center justify-between bg-indigo-50 border border-indigo-200 rounded-2xl p-2">
                  <div className="pl-3">
                    <p className="text-xs font-semibold text-indigo-950">In your cart</p>
                    <p className="text-xs text-indigo-700">
                      Total: {formatPrice(product.price_paise * cartQuantity)}
                    </p>
                  </div>
                  <div className="inline-flex items-center space-x-2">
                    <button
                      onClick={() => onUpdateCartQuantity(product, cartQuantity - 1)}
                      className="w-8 h-8 rounded-xl bg-white text-indigo-700 hover:bg-indigo-600 hover:text-white transition flex items-center justify-center shadow-xs"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <span className="w-8 text-center font-extrabold text-sm text-indigo-950">
                      {cartQuantity}
                    </span>
                    <button
                      onClick={() => {
                        if (cartQuantity < product.qty_available) {
                          onUpdateCartQuantity(product, cartQuantity + 1);
                        }
                      }}
                      disabled={cartQuantity >= product.qty_available}
                      className="w-8 h-8 rounded-xl bg-white text-indigo-700 hover:bg-indigo-600 hover:text-white transition flex items-center justify-center shadow-xs disabled:opacity-40"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => onAddToCart(product)}
                  className="w-full flex items-center justify-center space-x-2 bg-indigo-600 hover:bg-indigo-700 active:scale-98 text-white font-bold py-3.5 px-6 rounded-2xl shadow-lg shadow-indigo-600/25 transition text-sm"
                >
                  <ShoppingBag className="w-4 h-4" />
                  <span>Add to Cart ({formatPrice(product.price_paise)})</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
