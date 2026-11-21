import React from 'react';
import {
  Star,
  Plus,
  Minus,
  Check,
  AlertTriangle,
  XCircle,
  Eye,
  ShoppingBag,
} from 'lucide-react';
import type { ProductSearchResultItem } from '../types';
import {
  formatPrice,
  getOriginalPrice,
  getProductImage,
  getProductRating,
} from '../utils/format';

interface ProductCardProps {
  product: ProductSearchResultItem;
  cartQuantity: number;
  onAddToCart: (product: ProductSearchResultItem) => void;
  onUpdateCartQuantity: (product: ProductSearchResultItem, quantity: number) => void;
  onViewDetails: (product: ProductSearchResultItem) => void;
}

export const ProductCard: React.FC<ProductCardProps> = ({
  product,
  cartQuantity,
  onAddToCart,
  onUpdateCartQuantity,
  onViewDetails,
}) => {
  const { rating, reviews } = getProductRating(product.sku);
  const isInStock = product.is_in_stock && product.qty_available > 0;
  const isLowStock = isInStock && product.qty_available <= 5;
  const imageSrc = getProductImage(product.sku, product.category, product.image_url);

  return (
    <div className="group relative bg-white rounded-2xl border border-slate-200/90 shadow-xs hover:shadow-xl hover:border-indigo-300 transition-all duration-300 flex flex-col overflow-hidden">
      {/* Product Image Section */}
      <div className="relative aspect-square w-full bg-slate-50 overflow-hidden cursor-pointer" onClick={() => onViewDetails(product)}>
        <img
          src={imageSrc}
          alt={product.name}
          loading="lazy"
          className="w-full h-full object-cover object-center group-hover:scale-105 transition-transform duration-500 ease-out"
        />

        {/* Stock Badge Overlay */}
        <div className="absolute top-2.5 left-2.5">
          {!isInStock ? (
            <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-slate-900/80 backdrop-blur-xs text-rose-400 border border-rose-500/30 shadow-xs">
              <XCircle className="w-3 h-3 text-rose-400" />
              <span>Out of Stock</span>
            </span>
          ) : isLowStock ? (
            <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/90 backdrop-blur-xs text-white shadow-xs">
              <AlertTriangle className="w-3 h-3 text-white" />
              <span>Only {product.qty_available} left!</span>
            </span>
          ) : (
            <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-600/90 backdrop-blur-xs text-white shadow-xs">
              <Check className="w-3 h-3 text-white" />
              <span>In Stock ({product.qty_available})</span>
            </span>
          )}
        </div>

        {/* Quick View Button on Hover */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onViewDetails(product);
          }}
          className="absolute top-2.5 right-2.5 w-8 h-8 rounded-full bg-white/90 backdrop-blur-xs text-slate-700 hover:text-indigo-600 hover:bg-white shadow-md flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all"
          title="Quick View Specifications"
        >
          <Eye className="w-4 h-4" />
        </button>
      </div>

      {/* Product Details Section */}
      <div className="p-4 sm:p-5 flex-1 flex flex-col justify-between">
        <div>
          {/* Brand & Category row */}
          <div className="flex items-center space-x-2 text-[11px] font-semibold text-slate-500 mb-1.5 uppercase tracking-wider">
            {product.brand && (
              <span className="text-indigo-600 hover:underline">{product.brand}</span>
            )}
            {product.brand && product.category && <span>•</span>}
            {product.category && <span>{product.category}</span>}
          </div>

          {/* Product Title */}
          <h3
            onClick={() => onViewDetails(product)}
            className="text-sm sm:text-base font-bold text-slate-900 hover:text-indigo-600 cursor-pointer transition line-clamp-2 leading-snug"
            title={product.name}
          >
            {product.name}
          </h3>

          {/* Ratings & Reviews */}
          <div className="flex items-center space-x-1.5 mt-2">
            <div className="flex items-center text-amber-500">
              <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
            </div>
            <span className="text-xs font-bold text-slate-800">{rating}</span>
            <span className="text-xs text-slate-400">({reviews})</span>
          </div>
        </div>

        {/* Price & Add to Cart Action */}
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
          {/* Price */}
          <div>
            <div className="flex items-baseline space-x-1.5">
              <span className="text-base sm:text-lg font-black text-slate-900">
                {formatPrice(product.price_paise)}
              </span>
              <span className="text-xs text-slate-400 line-through">
                {getOriginalPrice(product.price_paise)}
              </span>
            </div>
            <p className="text-[10px] text-emerald-600 font-semibold">Free 15-min delivery</p>
          </div>

          {/* Interactive Add to Cart Controls */}
          <div>
            {!isInStock ? (
              <button
                disabled
                className="px-3 py-1.5 rounded-xl bg-slate-100 text-slate-400 font-semibold text-xs cursor-not-allowed border border-slate-200"
              >
                Sold Out
              </button>
            ) : cartQuantity > 0 ? (
              <div className="inline-flex items-center bg-indigo-50 border border-indigo-200 rounded-xl p-0.5 shadow-xs">
                <button
                  onClick={() => onUpdateCartQuantity(product, cartQuantity - 1)}
                  className="w-7 h-7 rounded-lg bg-white text-indigo-700 hover:bg-indigo-600 hover:text-white transition flex items-center justify-center shadow-xs"
                  title="Decrease Quantity"
                >
                  <Minus className="w-3.5 h-3.5" />
                </button>
                <span className="w-7 text-center font-bold text-xs text-indigo-900">
                  {cartQuantity}
                </span>
                <button
                  onClick={() => {
                    if (cartQuantity < product.qty_available) {
                      onUpdateCartQuantity(product, cartQuantity + 1);
                    }
                  }}
                  disabled={cartQuantity >= product.qty_available}
                  className="w-7 h-7 rounded-lg bg-white text-indigo-700 hover:bg-indigo-600 hover:text-white transition flex items-center justify-center shadow-xs disabled:opacity-40 disabled:cursor-not-allowed"
                  title="Increase Quantity"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => onAddToCart(product)}
                className="flex items-center space-x-1.5 bg-indigo-600 hover:bg-indigo-700 active:scale-95 text-white font-bold text-xs px-3.5 py-2 rounded-xl shadow-xs shadow-indigo-600/20 transition duration-150"
              >
                <ShoppingBag className="w-3.5 h-3.5" />
                <span>Add</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
