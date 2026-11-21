import React from 'react';
import {
  SlidersHorizontal,
  RotateCcw,
  ArrowUpDown,
  CheckSquare,
  Square,
  X,
} from 'lucide-react';
import type { SearchFilterFacets, SortOption } from '../types';
import { formatPrice } from '../utils/format';

interface FilterSidebarProps {
  facets: SearchFilterFacets;
  selectedCategory: string | null;
  onSelectCategory: (category: string | null) => void;
  selectedBrand: string | null;
  onSelectBrand: (brand: string | null) => void;
  inStockOnly: boolean;
  onToggleInStockOnly: (value: boolean) => void;
  sortBy: SortOption;
  onChangeSortBy: (sort: SortOption) => void;
  onResetFilters: () => void;
  totalResults: number;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  facets,
  selectedCategory,
  onSelectCategory,
  selectedBrand,
  onSelectBrand,
  inStockOnly,
  onToggleInStockOnly,
  sortBy,
  onChangeSortBy,
  onResetFilters,
  totalResults,
  isOpenMobile = false,
  onCloseMobile,
}) => {
  const hasActiveFilters =
    Boolean(selectedCategory) || Boolean(selectedBrand) || inStockOnly || sortBy !== 'relevance';

  const content = (
    <div className="space-y-6">
      {/* Filter Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-200">
        <div className="flex items-center space-x-2">
          <SlidersHorizontal className="w-4 h-4 text-indigo-600" />
          <h2 className="font-bold text-sm text-slate-900 uppercase tracking-wider">
            Filters & Sorting
          </h2>
        </div>
        {hasActiveFilters && (
          <button
            onClick={onResetFilters}
            className="flex items-center space-x-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset</span>
          </button>
        )}
      </div>

      {/* Sort By Dropdown */}
      <div>
        <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 flex items-center space-x-1">
          <ArrowUpDown className="w-3.5 h-3.5 text-indigo-500" />
          <span>Sort By</span>
        </label>
        <select
          value={sortBy}
          onChange={(e) => onChangeSortBy(e.target.value as SortOption)}
          className="w-full text-xs font-medium bg-slate-50 border border-slate-300 rounded-xl px-3 py-2 text-slate-800 focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-hidden transition cursor-pointer"
        >
          <option value="relevance">Relevance & Best Matches</option>
          <option value="price_asc">Price: Low to High</option>
          <option value="price_desc">Price: High to Low</option>
          <option value="name_asc">Product Name (A-Z)</option>
          <option value="newest">Newest Arrivals</option>
        </select>
      </div>

      {/* In-Stock Only Toggle */}
      <div className="pt-2">
        <label className="flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-slate-100/70 border border-slate-200 cursor-pointer transition">
          <span className="text-xs font-semibold text-slate-800">In Stock Only</span>
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(e) => onToggleInStockOnly(e.target.checked)}
            className="w-4 h-4 text-indigo-600 rounded-sm border-slate-300 focus:ring-indigo-500 cursor-pointer"
          />
        </label>
      </div>

      {/* Category Facets */}
      <div>
        <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5">
          Categories
        </h3>
        <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
          <button
            onClick={() => onSelectCategory(null)}
            className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs transition ${
              selectedCategory === null
                ? 'bg-indigo-50 text-indigo-700 font-bold'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            <span>All Categories</span>
            <span className="text-[11px] text-slate-400">({totalResults})</span>
          </button>
          {facets.categories.map((cat) => {
            const isSelected = selectedCategory?.toLowerCase() === cat.name.toLowerCase();
            return (
              <button
                key={cat.name}
                onClick={() => onSelectCategory(isSelected ? null : cat.name)}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs capitalize transition ${
                  isSelected
                    ? 'bg-indigo-50 text-indigo-700 font-bold'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <div className="flex items-center space-x-2 truncate">
                  {isSelected ? (
                    <CheckSquare className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                  ) : (
                    <Square className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  )}
                  <span className="truncate">{cat.name}</span>
                </div>
                <span className="text-[11px] text-slate-400 shrink-0">({cat.count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Brand Facets */}
      {facets.brands && facets.brands.length > 0 && (
        <div className="pt-2 border-t border-slate-200">
          <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5">
            Brands
          </h3>
          <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
            {facets.brands.map((brand) => {
              const isSelected = selectedBrand?.toLowerCase() === brand.name.toLowerCase();
              return (
                <button
                  key={brand.name}
                  onClick={() => onSelectBrand(isSelected ? null : brand.name)}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs capitalize transition ${
                    isSelected
                      ? 'bg-indigo-50 text-indigo-700 font-bold'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  <div className="flex items-center space-x-2 truncate">
                    {isSelected ? (
                      <CheckSquare className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                    ) : (
                      <Square className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    )}
                    <span className="truncate">{brand.name}</span>
                  </div>
                  <span className="text-[11px] text-slate-400 shrink-0">({brand.count})</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Price Facet Range Bounds */}
      {facets.max_price_paise > 0 && (
        <div className="pt-2 border-t border-slate-200">
          <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
            Store Price Bounds
          </h3>
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs text-slate-600 space-y-1">
            <div className="flex justify-between">
              <span>Lowest:</span>
              <span className="font-bold text-slate-900">{formatPrice(facets.min_price_paise)}</span>
            </div>
            <div className="flex justify-between">
              <span>Highest:</span>
              <span className="font-bold text-slate-900">{formatPrice(facets.max_price_paise)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:block w-64 bg-white p-5 rounded-2xl border border-slate-200/90 shadow-xs shrink-0 self-start sticky top-28">
        {content}
      </aside>

      {/* Mobile Drawer */}
      {isOpenMobile && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div
            className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity"
            onClick={onCloseMobile}
          />
          <div className="relative ml-auto w-full max-w-xs bg-white h-full p-6 shadow-2xl flex flex-col justify-between overflow-y-auto">
            <div>
              <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-200">
                <h2 className="font-bold text-base text-slate-900">Filters</h2>
                <button
                  onClick={onCloseMobile}
                  className="p-1.5 text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-100"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              {content}
            </div>
            <div className="pt-6 mt-6 border-t border-slate-200">
              <button
                onClick={onCloseMobile}
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 rounded-xl shadow-xs transition"
              >
                Apply Filters ({totalResults} products)
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
