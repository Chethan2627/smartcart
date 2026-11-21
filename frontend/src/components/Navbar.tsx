import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  MapPin,
  ShoppingCart,
  User,
  ChevronDown,
  X,
  Check,
  Sparkles,
  Clock,
  LogOut,
  Store as StoreIcon,
  Shield,
} from 'lucide-react';
import type { Store, SearchSuggestionItem } from '../types';
import { fetchSearchSuggestions } from '../api/client';
import { formatPrice, getProductImage } from '../utils/format';
import { useAuth } from '../context/useAuth';
import { useCart } from '../context/useCart';

interface NavbarProps {
  stores: Store[];
  currentStore: Store | null;
  onSelectStore: (store: Store) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onSearchSubmit: (query: string) => void;
  cartCount: number;
  onOpenCartSummary?: () => void;
  onSelectSuggestionProduct?: (productId: string) => void;
  onNavigateToManager?: () => void;
  onNavigateToAdmin?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  stores,
  currentStore,
  onSelectStore,
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  cartCount,
  onOpenCartSummary,
  onSelectSuggestionProduct,
  onNavigateToManager,
  onNavigateToAdmin,
}) => {
  const [storeDropdownOpen, setStoreDropdownOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<SearchSuggestionItem[]>([]);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);

  const searchContainerRef = useRef<HTMLDivElement>(null);
  const storeSelectorRef = useRef<HTMLDivElement>(null);
  const userDropdownRef = useRef<HTMLDivElement>(null);

  const { user, isAuthenticated, logout, promptAuth } = useAuth();
  const { totalItems: cartTotalItems, setIsCartOpen, reservationTimer } = useCart();
  const effectiveCartCount = cartCount || cartTotalItems;

  // Debounced autocomplete suggestions lookup
  useEffect(() => {
    const timer = setTimeout(async () => {
      if (!currentStore || searchQuery.trim().length < 2) {
        setSuggestions([]);
        setSuggestionsOpen(false);
        return;
      }

      setIsSuggesting(true);
      try {
        const resp = await fetchSearchSuggestions(currentStore.id, searchQuery, 6);
        setSuggestions(resp.suggestions || []);
        setSuggestionsOpen((resp.suggestions || []).length > 0);
      } catch (err) {
        console.warn('Autocomplete suggestions lookup failed:', err);
      } finally {
        setIsSuggesting(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery, currentStore]);

  // Click outside listener for dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setSuggestionsOpen(false);
      }
      if (
        storeSelectorRef.current &&
        !storeSelectorRef.current.contains(e.target as Node)
      ) {
        setStoreDropdownOpen(false);
      }
      if (
        userDropdownRef.current &&
        !userDropdownRef.current.contains(e.target as Node)
      ) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      setSuggestionsOpen(false);
      onSearchSubmit(searchQuery);
    } else if (e.key === 'Escape') {
      setSuggestionsOpen(false);
    }
  };

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/80 shadow-xs">
      {/* Top Banner: Quick delivery & zero-overselling guarantee */}
      <div className="bg-gradient-to-r from-indigo-900 via-slate-900 to-indigo-950 text-indigo-100 text-xs py-1.5 px-4 text-center font-medium flex items-center justify-center space-x-2">
        <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
        <span>Instant Local Delivery in 15 Minutes • Zero-Overselling Inventory Hold Guarantee</span>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 sm:h-20 gap-4">
          {/* 1. Brand Logo */}
          <div className="flex items-center space-x-3 shrink-0">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-700 to-violet-600 flex items-center justify-center text-white font-extrabold text-xl shadow-md shadow-indigo-500/20 ring-2 ring-indigo-500/30">
              S
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold text-xl tracking-tight text-slate-900">
                  Smart<span className="text-indigo-600">Cart</span>
                </span>
                <span className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                  v2.0
                </span>
              </div>
              <p className="text-[11px] text-slate-500 hidden sm:block">Aiven Cloud Commerce</p>
            </div>
          </div>

          {/* 2. Store Fulfillment Selector */}
          <div className="relative shrink-0" ref={storeSelectorRef}>
            <button
              onClick={() => setStoreDropdownOpen(!storeDropdownOpen)}
              className="flex items-center space-x-2 text-left bg-slate-100 hover:bg-slate-200/80 text-slate-800 px-3 py-2 rounded-xl transition border border-slate-200 text-xs sm:text-sm font-medium"
              title="Change Fulfillment Store"
            >
              <div className="w-6 h-6 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                <MapPin className="w-3.5 h-3.5" />
              </div>
              <div className="hidden md:block">
                <p className="text-[10px] text-slate-500 uppercase font-semibold leading-none">Delivering from</p>
                <p className="font-semibold text-slate-900 leading-tight truncate max-w-[140px]">
                  {currentStore?.name || 'Select Store'}
                </p>
              </div>
              <ChevronDown className="w-4 h-4 text-slate-400" />
            </button>

            {/* Store Selection Dropdown */}
            {storeDropdownOpen && (
              <div className="absolute left-0 mt-2 w-72 bg-white rounded-2xl shadow-xl border border-slate-200 py-2 z-50 animate-in fade-in slide-in-from-top-2">
                <div className="px-4 py-2 border-b border-slate-100">
                  <p className="text-xs font-bold text-slate-900">Choose Fulfillment Store</p>
                  <p className="text-[11px] text-slate-500">Live store stock updates automatically</p>
                </div>
                <div className="max-h-64 overflow-y-auto py-1">
                  {stores.map((store) => {
                    const isSelected = currentStore?.id === store.id;
                    return (
                      <button
                        key={store.id}
                        onClick={() => {
                          onSelectStore(store);
                          setStoreDropdownOpen(false);
                        }}
                        className={`w-full text-left px-4 py-2.5 flex items-center justify-between text-xs transition hover:bg-indigo-50/70 ${
                          isSelected ? 'bg-indigo-50/90 text-indigo-900 font-semibold' : 'text-slate-700'
                        }`}
                      >
                        <div>
                          <p className="font-semibold">{store.name}</p>
                          <p className="text-[11px] text-slate-500">
                            {store.city}, {store.state} • {store.code}
                          </p>
                        </div>
                        {isSelected && <Check className="w-4 h-4 text-indigo-600 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* 3. Central Search Bar with Autocomplete */}
          <div className="relative flex-1 max-w-2xl" ref={searchContainerRef}>
            <div className="relative flex items-center">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => onSearchChange(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => {
                  if (suggestions.length > 0) setSuggestionsOpen(true);
                }}
                placeholder="Search groceries, electronics, mobiles, brands with typo-tolerance..."
                className="w-full pl-10 pr-10 py-2.5 text-xs sm:text-sm bg-slate-100 hover:bg-slate-100/80 focus:bg-white text-slate-900 rounded-full border border-slate-200 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 outline-hidden transition shadow-xs"
              />
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 pointer-events-none" />

              {searchQuery ? (
                <button
                  onClick={() => {
                    onSearchChange('');
                    setSuggestions([]);
                    setSuggestionsOpen(false);
                  }}
                  className="absolute right-3 p-1 text-slate-400 hover:text-slate-600 rounded-full"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              ) : isSuggesting ? (
                <div className="absolute right-3.5 w-3.5 h-3.5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              ) : null}
            </div>

            {/* Live Autocomplete Suggestions Dropdown */}
            {suggestionsOpen && suggestions.length > 0 && (
              <div className="absolute left-0 right-0 mt-2 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden z-50 animate-in fade-in slide-in-from-top-1">
                <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center justify-between text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                  <span>Product Suggestions</span>
                  <span>OpenSearch Edge N-Gram</span>
                </div>
                <div className="divide-y divide-slate-100 max-h-80 overflow-y-auto">
                  {suggestions.map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setSuggestionsOpen(false);
                        if (onSelectSuggestionProduct) {
                          onSelectSuggestionProduct(item.product_id);
                        } else {
                          onSearchSubmit(item.text);
                        }
                      }}
                      className="w-full text-left px-4 py-2.5 flex items-center space-x-3 hover:bg-indigo-50/60 transition group"
                    >
                      <img
                        src={getProductImage(item.sku, item.category)}
                        alt={item.text}
                        className="w-10 h-10 object-cover rounded-lg border border-slate-200 shrink-0 group-hover:scale-105 transition"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs sm:text-sm font-semibold text-slate-900 truncate group-hover:text-indigo-600">
                          {item.text}
                        </p>
                        <p className="text-[11px] text-slate-500">
                          {item.brand && <span className="font-medium text-slate-700">{item.brand} • </span>}
                          {item.category}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        {item.price_paise !== undefined && item.price_paise !== null && (
                          <p className="text-xs sm:text-sm font-bold text-slate-900">
                            {formatPrice(item.price_paise)}
                          </p>
                        )}
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                            item.is_in_stock
                              ? 'bg-emerald-50 text-emerald-700'
                              : 'bg-rose-50 text-rose-700'
                          }`}
                        >
                          {item.is_in_stock ? 'In Stock' : 'Out of Stock'}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="p-2 bg-slate-50 border-t border-slate-100 text-center">
                  <button
                    onClick={() => {
                      setSuggestionsOpen(false);
                      onSearchSubmit(searchQuery);
                    }}
                    className="text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    View all matching results →
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* 4. Customer Actions: Reservation Timer, Cart & Account */}
          <div className="flex items-center space-x-2 sm:space-x-3 shrink-0">
            {/* Live Stock Reservation Countdown Pill */}
            {reservationTimer && !reservationTimer.isExpired && effectiveCartCount > 0 && (
              <button
                type="button"
                onClick={() => (onOpenCartSummary ? onOpenCartSummary() : setIsCartOpen(true))}
                className={`hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-semibold border transition ${
                  reservationTimer.isUrgent
                    ? 'bg-red-50 text-red-700 border-red-200 animate-pulse'
                    : reservationTimer.isWarning
                    ? 'bg-amber-50 text-amber-800 border-amber-200'
                    : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                }`}
                title="Active 10-minute PostgreSQL reservation hold"
              >
                <Clock className="w-3.5 h-3.5 shrink-0" />
                <span>Hold: {reservationTimer.formattedTime}</span>
              </button>
            )}

            {/* Cart Trigger */}
            <button
              type="button"
              onClick={() => (onOpenCartSummary ? onOpenCartSummary() : setIsCartOpen(true))}
              className="relative flex items-center space-x-2 bg-emerald-50 hover:bg-emerald-100 text-emerald-900 px-3 py-2 rounded-xl transition border border-emerald-200 font-semibold text-xs sm:text-sm"
              title="Shopping Cart & Stock Reservations"
            >
              <ShoppingCart className="w-4 h-4 text-emerald-600" />
              <span className="hidden sm:inline">Cart</span>
              {effectiveCartCount > 0 ? (
                <span className="absolute -top-1.5 -right-1.5 bg-emerald-600 text-white font-extrabold text-[10px] w-5 h-5 rounded-full flex items-center justify-center shadow-md animate-scale">
                  {effectiveCartCount}
                </span>
              ) : null}
            </button>

            {/* Manager Portal Shortcut for Store Managers */}
            {isAuthenticated && user?.role === 'STORE_MANAGER' && (
              <button
                type="button"
                onClick={onNavigateToManager}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition shadow-xs"
                title="Store Manager Dashboard"
              >
                <StoreIcon className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden sm:inline">Manager Portal</span>
              </button>
            )}

            {/* Admin Console Shortcut for Admins & Super Admins */}
            {isAuthenticated &&
              (user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN') && (
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={onNavigateToAdmin}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-purple-900 hover:bg-purple-800 text-white text-xs font-bold transition shadow-xs border border-purple-700/60"
                    title="System Admin Dashboard"
                  >
                    <Shield className="w-3.5 h-3.5 text-purple-300" />
                    <span className="hidden sm:inline">Admin Console</span>
                  </button>
                  <button
                    type="button"
                    onClick={onNavigateToManager}
                    className="hidden xl:flex items-center gap-1.5 px-2.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold transition shadow-xs"
                    title="Store Manager Dashboard"
                  >
                    <StoreIcon className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Manager View</span>
                  </button>
                </div>
              )}

            {/* User Account / Auth Dropdown */}
            {isAuthenticated ? (
              <div className="relative" ref={userDropdownRef}>
                <button
                  type="button"
                  onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                  className="flex items-center space-x-1.5 bg-slate-100 hover:bg-slate-200/80 text-slate-800 p-2 sm:px-3 sm:py-2 rounded-xl transition border border-slate-200 text-xs font-medium"
                >
                  <User className="w-4 h-4 text-emerald-600" />
                  <span className="hidden md:inline font-semibold max-w-28 truncate">
                    {user?.full_name || 'Customer'}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                </button>

                {userDropdownOpen && (
                  <div className="absolute right-0 mt-2 w-56 bg-white rounded-2xl shadow-2xl border border-gray-100 py-2 z-50 text-xs animate-in fade-in slide-in-from-top-1">
                    <div className="px-3.5 py-2.5 border-b border-gray-100">
                      <p className="font-semibold text-gray-900 truncate">{user?.full_name}</p>
                      <p className="text-gray-500 text-[11px] truncate">{user?.email}</p>
                      <span className="inline-block mt-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold tracking-wider">
                        {user?.role}
                      </span>
                    </div>

                    <div className="py-1">
                      {(user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN') && (
                        <button
                          type="button"
                          onClick={() => {
                            setUserDropdownOpen(false);
                            if (onNavigateToAdmin) onNavigateToAdmin();
                          }}
                          className="w-full text-left px-3.5 py-2 hover:bg-purple-50 text-purple-800 flex items-center gap-2 font-semibold"
                        >
                          <Shield className="w-3.5 h-3.5 text-purple-600" />
                          <span>Admin Console</span>
                        </button>
                      )}

                      {(user?.role === 'STORE_MANAGER' ||
                        user?.role === 'ADMIN' ||
                        user?.role === 'SUPER_ADMIN') && (
                        <button
                          type="button"
                          onClick={() => {
                            setUserDropdownOpen(false);
                            if (onNavigateToManager) onNavigateToManager();
                          }}
                          className="w-full text-left px-3.5 py-2 hover:bg-emerald-50 text-emerald-800 flex items-center gap-2 font-semibold"
                        >
                          <StoreIcon className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Manager Portal</span>
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => {
                          setUserDropdownOpen(false);
                          setIsCartOpen(true);
                        }}
                        className="w-full text-left px-3.5 py-2 hover:bg-emerald-50 text-gray-700 flex items-center gap-2"
                      >
                        <ShoppingCart className="w-3.5 h-3.5 text-gray-400" />
                        <span>View Cart ({effectiveCartCount})</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setUserDropdownOpen(false);
                          logout();
                        }}
                        className="w-full text-left px-3.5 py-2 hover:bg-red-50 text-red-600 flex items-center gap-2 font-medium"
                      >
                        <LogOut className="w-3.5 h-3.5" />
                        <span>Sign Out</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => promptAuth()}
                className="flex items-center space-x-1.5 bg-emerald-600 hover:bg-emerald-700 text-white px-3 sm:px-3.5 py-2 rounded-xl transition text-xs font-semibold shadow-xs"
              >
                <User className="w-4 h-4" />
                <span>Sign In</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
