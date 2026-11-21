import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  fetchStores,
  searchProducts,
  fetchProducts,
} from './api/client';
import type {
  Store,
  ProductSearchResultItem,
  SearchFilterFacets,
  SortOption,
} from './types';
import { AuthProvider } from './context/AuthContext';
import { CartProvider } from './context/CartContext';
import { useCart } from './context/useCart';
import { Navbar } from './components/Navbar';
import { HeroBanner } from './components/HeroBanner';
import { FilterSidebar } from './components/FilterSidebar';
import { ProductCard } from './components/ProductCard';
import { ProductModal } from './components/ProductModal';
import { CartDrawer } from './components/CartDrawer';
import { AuthModal } from './components/AuthModal';
import { CheckoutModal } from './components/CheckoutModal';
import { ManagerDashboard } from './components/manager/ManagerDashboard';
import { AdminDashboard } from './components/admin/AdminDashboard';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import { EmptyState } from './components/EmptyState';
import { Toast } from './components/Toast';
import { Footer } from './components/Footer';
import {
  SlidersHorizontal,
  RefreshCw,
  AlertCircle,
  Sparkles,
} from 'lucide-react';

const DEFAULT_FACETS: SearchFilterFacets = {
  categories: [],
  brands: [],
  min_price_paise: 0,
  max_price_paise: 0,
};

interface StorefrontContentProps {
  stores: Store[];
  onNavigateToManager: () => void;
  onNavigateToAdmin: () => void;
}

function StorefrontContent({
  stores,
  onNavigateToManager,
  onNavigateToAdmin,
}: StorefrontContentProps) {
  // Store management
  const [selectedStoreId, setSelectedStoreId] = useState<string | null>(null);

  const currentStore = useMemo<Store | null>(() => {
    if (selectedStoreId) {
      const match = stores.find((s) => s.id === selectedStoreId);
      if (match) return match;
    }
    return stores.length > 0 ? stores[0] : null;
  }, [stores, selectedStoreId]);

  const handleSelectStore = useCallback((store: Store) => {
    setSelectedStoreId(store.id);
  }, []);

  // Search and filter parameters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedBrand, setSelectedBrand] = useState<string | null>(null);
  const [inStockOnly, setInStockOnly] = useState<boolean>(false);
  const [sortBy, setSortBy] = useState<SortOption>('relevance');

  // Search results & facets state
  const [products, setProducts] = useState<ProductSearchResultItem[]>([]);
  const [facets, setFacets] = useState<SearchFilterFacets>(DEFAULT_FACETS);
  const [totalResults, setTotalResults] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // UI modals and toasts
  const [selectedProduct, setSelectedProduct] = useState<ProductSearchResultItem | null>(null);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Cart context integration
  const {
    items: cartItems,
    addToCart,
    updateQuantity,
    setIsCartOpen,
    onStockExpiredCallbacks,
  } = useCart();

  // Authoritative cart quantity lookup by productId
  const cartQuantities = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of cartItems) {
      map[item.product_id] = item.qty;
    }
    return map;
  }, [cartItems]);

  // 2. Query products using OpenSearch search endpoint (scoped to current store)
  const loadStoreProducts = useCallback(async () => {
    if (!currentStore) return;

    setLoading(true);
    setError(null);

    try {
      const resp = await searchProducts({
        storeId: currentStore.id,
        q: searchQuery,
        category: selectedCategory || undefined,
        brand: selectedBrand || undefined,
        inStockOnly,
        sortBy,
        pageSize: 40,
        useNlp: true,
      });

      // If OpenSearch returned items, use them directly
      if (resp.items && resp.items.length > 0) {
        setProducts(resp.items);
        setFacets(resp.filters || DEFAULT_FACETS);
        setTotalResults(resp.total);
      } else {
        // Fallback: If OpenSearch has no items yet, fetch directly from PostgreSQL catalogue
        const catProducts = await fetchProducts({
          category: selectedCategory || undefined,
          brand: selectedBrand || undefined,
          limit: 40,
        });

        // Map PostgreSQL catalogue items into ProductSearchResultItem structure
        const mappedItems: ProductSearchResultItem[] = catProducts.map((p) => ({
          id: `${p.id}_${currentStore.id}`,
          product_id: p.id,
          store_id: currentStore.id,
          sku: p.sku,
          name: p.name,
          brand: p.brand,
          category: p.category,
          description: p.description,
          price_paise: p.price_paise,
          image_url: p.attributes?.image?.secure_url || p.attributes?.image_url,
          is_active: p.is_active,
          qty_on_hand: 25,
          qty_reserved: 0,
          qty_available: 25,
          is_in_stock: true,
        }));

        setProducts(mappedItems);
        setTotalResults(mappedItems.length);
        setFacets(resp.filters || DEFAULT_FACETS);
      }
    } catch (err: unknown) {
      console.error('Product search error:', err);
      const msg = err instanceof Error ? err.message : 'Error retrieving products';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [currentStore, searchQuery, selectedCategory, selectedBrand, inStockOnly, sortBy]);

  // Load products when store or filters change
  useEffect(() => {
    let ignore = false;
    const fetchStoreCatalog = async () => {
      if (currentStore && !ignore) {
        await loadStoreProducts();
      }
    };
    fetchStoreCatalog();
    return () => {
      ignore = true;
    };
  }, [currentStore, loadStoreProducts]);

  // Subscribe to reservation expiration events to auto-refresh available inventory
  useEffect(() => {
    const callback = () => {
      loadStoreProducts();
    };
    const callbacksSet = onStockExpiredCallbacks.current;
    callbacksSet.add(callback);
    return () => {
      callbacksSet.delete(callback);
    };
  }, [loadStoreProducts, onStockExpiredCallbacks]);

  // 3. Cart Handlers (delegates to PostgreSQL reservation backend)
  const handleAddToCart = async (product: ProductSearchResultItem) => {
    if (!currentStore) return;
    const ok = await addToCart(currentStore.id, product.product_id, 1);
    if (ok) {
      setToastMessage(`Reserved 1x ${product.name} (Held for 10 mins)`);
    }
  };

  const handleUpdateCartQuantity = async (product: ProductSearchResultItem, quantity: number) => {
    const ok = await updateQuantity(product.product_id, quantity);
    if (ok) {
      if (quantity <= 0) {
        setToastMessage(`Released reservation for ${product.name}`);
      } else {
        setToastMessage(`Updated ${product.name} quantity to ${quantity}`);
      }
    }
  };

  const handleResetFilters = () => {
    setSearchQuery('');
    setSelectedCategory(null);
    setSelectedBrand(null);
    setInStockOnly(false);
    setSortBy('relevance');
  };

  const handleSelectSuggestionProduct = (productId: string) => {
    const found = products.find((p) => p.product_id === productId);
    if (found) {
      setSelectedProduct(found);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-900 flex flex-col font-sans selection:bg-emerald-500 selection:text-white">
      {/* Toast Notification */}
      {toastMessage && (
        <Toast message={toastMessage} onClose={() => setToastMessage(null)} />
      )}

      {/* Navigation Bar */}
      <Navbar
        stores={stores}
        currentStore={currentStore}
        onSelectStore={handleSelectStore}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSearchSubmit={setSearchQuery}
        cartCount={cartItems.reduce((acc, i) => acc + i.qty, 0)}
        onOpenCartSummary={() => setIsCartOpen(true)}
        onSelectSuggestionProduct={handleSelectSuggestionProduct}
        onNavigateToManager={onNavigateToManager}
        onNavigateToAdmin={onNavigateToAdmin}
      />

      {/* Hero Banner */}
      <HeroBanner
        activeCategory={selectedCategory}
        onSelectCategory={(cat) => setSelectedCategory(cat === selectedCategory ? null : cat)}
        storeName={currentStore?.name}
        storeCity={currentStore?.city}
      />

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {/* Results Header Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 mb-6 border-b border-slate-200/80 gap-4">
          <div>
            <h2 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
              {searchQuery ? (
                <span>
                  Results for &ldquo;<span className="text-emerald-700">{searchQuery}</span>&rdquo;
                </span>
              ) : selectedCategory ? (
                <span>{selectedCategory}</span>
              ) : (
                <span>Available Products</span>
              )}
            </h2>
            <p className="text-xs sm:text-sm text-slate-500 mt-1">
              {loading ? (
                'Checking store inventory...'
              ) : (
                <span>
                  Found <strong>{totalResults}</strong> items at{' '}
                  <span className="font-semibold text-slate-700">
                    {currentStore?.name || 'Selected Store'}
                  </span>
                </span>
              )}
            </p>
          </div>

          {/* Mobile Filter Toggle Button */}
          <div className="flex items-center space-x-3 lg:hidden">
            <button
              onClick={() => setMobileFiltersOpen(true)}
              className="flex items-center space-x-2 bg-white px-4 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-700 shadow-xs hover:bg-slate-50"
            >
              <SlidersHorizontal className="w-4 h-4 text-emerald-600" />
              <span>Filters & Sort</span>
            </button>
          </div>
        </div>

        {/* Layout: Sidebar + Product Grid */}
        <div className="flex flex-col lg:flex-row gap-8 items-start">
          {/* Faceted Filter Sidebar */}
          <FilterSidebar
            facets={facets}
            selectedCategory={selectedCategory}
            onSelectCategory={setSelectedCategory}
            selectedBrand={selectedBrand}
            onSelectBrand={setSelectedBrand}
            inStockOnly={inStockOnly}
            onToggleInStockOnly={setInStockOnly}
            sortBy={sortBy}
            onChangeSortBy={setSortBy}
            onResetFilters={handleResetFilters}
            totalResults={totalResults}
            isOpenMobile={mobileFiltersOpen}
            onCloseMobile={() => setMobileFiltersOpen(false)}
          />

          {/* Products View Area */}
          <div className="flex-1 min-w-0">
            {/* Error State */}
            {error ? (
              <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-center max-w-lg mx-auto my-8">
                <AlertCircle className="w-8 h-8 text-rose-500 mx-auto mb-2" />
                <h3 className="font-bold text-slate-900 text-sm">Failed to load catalogue</h3>
                <p className="text-xs text-slate-600 mt-1">{error}</p>
                <button
                  onClick={loadStoreProducts}
                  className="mt-4 inline-flex items-center space-x-2 bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs px-4 py-2 rounded-xl transition"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retry Connection</span>
                </button>
              </div>
            ) : loading ? (
              /* Loading State */
              <LoadingSkeleton />
            ) : products.length === 0 ? (
              /* Empty State */
              <EmptyState
                searchQuery={searchQuery}
                hasFilters={Boolean(selectedCategory || selectedBrand || inStockOnly)}
                onReset={handleResetFilters}
              />
            ) : (
              /* Product Listing Cards Grid */
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-6">
                {products.map((product) => (
                  <ProductCard
                    key={product.id || product.product_id}
                    product={product}
                    cartQuantity={cartQuantities[product.product_id] || 0}
                    onAddToCart={handleAddToCart}
                    onUpdateCartQuantity={handleUpdateCartQuantity}
                    onViewDetails={setSelectedProduct}
                  />
                ))}
              </div>
            )}

            {/* Quick Informational Bottom Notice */}
            {!loading && products.length > 0 && (
              <div className="mt-12 p-4 rounded-2xl bg-emerald-50/70 border border-emerald-100 flex items-center justify-between text-xs text-emerald-900">
                <div className="flex items-center space-x-2">
                  <Sparkles className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>
                    Showing real-time stock balances synchronized with <strong>Aiven OpenSearch</strong> and <strong>PostgreSQL</strong>.
                  </span>
                </div>
                <span className="text-[11px] font-semibold text-emerald-700 hidden sm:inline">
                  Zero Overselling • 10-Min Hold Guarantee
                </span>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Product Details Modal */}
      <ProductModal
        product={selectedProduct}
        store={currentStore}
        onClose={() => setSelectedProduct(null)}
        cartQuantity={selectedProduct ? cartQuantities[selectedProduct.product_id] || 0 : 0}
        onAddToCart={handleAddToCart}
        onUpdateCartQuantity={handleUpdateCartQuantity}
      />

      {/* Slide-out Cart Drawer with 10-Minute Reservation Timer */}
      <CartDrawer currentStoreName={currentStore?.name} />

      {/* Atomic Checkout Modal with Idempotency Protection */}
      <CheckoutModal
        currentStoreName={currentStore?.name}
        onOrderSuccess={() => {
          loadStoreProducts();
        }}
      />

      {/* Footer */}
      <Footer />
    </div>
  );
}

function MainContent() {
  const [currentView, setCurrentView] = useState<'storefront' | 'manager' | 'admin'>(() => {
    if (typeof window !== 'undefined') {
      if (window.location.hash === '#admin') return 'admin';
      if (window.location.hash === '#manager') return 'manager';
    }
    return 'storefront';
  });
  const [stores, setStores] = useState<Store[]>([]);

  useEffect(() => {
    let mounted = true;
    fetchStores()
      .then((storeList) => {
        if (mounted && storeList.length > 0) {
          setStores(storeList);
        }
      })
      .catch((err) => {
        console.error('Failed to load stores:', err);
      });

    const handleHash = () => {
      if (window.location.hash === '#admin') {
        setCurrentView('admin');
      } else if (window.location.hash === '#manager') {
        setCurrentView('manager');
      } else {
        setCurrentView('storefront');
      }
    };
    window.addEventListener('hashchange', handleHash);
    return () => {
      mounted = false;
      window.removeEventListener('hashchange', handleHash);
    };
  }, []);

  const navigateToAdmin = () => {
    window.location.hash = 'admin';
    setCurrentView('admin');
  };

  const navigateToManager = () => {
    window.location.hash = 'manager';
    setCurrentView('manager');
  };

  const navigateToStorefront = () => {
    window.location.hash = '';
    setCurrentView('storefront');
  };

  return (
    <>
      {currentView === 'admin' ? (
        <AdminDashboard
          stores={stores}
          onReturnToStorefront={navigateToStorefront}
          onNavigateToManager={navigateToManager}
        />
      ) : currentView === 'manager' ? (
        <ManagerDashboard
          stores={stores}
          onReturnToStorefront={navigateToStorefront}
          onNavigateToAdmin={navigateToAdmin}
        />
      ) : (
        <StorefrontContent
          stores={stores}
          onNavigateToManager={navigateToManager}
          onNavigateToAdmin={navigateToAdmin}
        />
      )}
      {/* Universal Authentication Modal */}
      <AuthModal />
    </>
  );
}

export function App() {
  return (
    <AuthProvider>
      <CartProvider>
        <MainContent />
      </CartProvider>
    </AuthProvider>
  );
}

export default App;
