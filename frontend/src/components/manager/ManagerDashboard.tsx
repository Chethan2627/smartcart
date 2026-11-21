import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ShieldAlert,
  Loader2,
  Lock,
  ArrowLeft,
  Sparkles,
} from 'lucide-react';
import type { ManagerProduct, StockResponse, Store as StoreType } from '../../types';
import {
  fetchManagerProducts,
  fetchStoreInventory,
  fetchLowStockInventory,
  deactivateManagerProduct,
} from '../../api/client';
import { useAuth } from '../../context/useAuth';
import { ManagerLayout, type ManagerTab } from './ManagerLayout';
import { ManagerOverview } from './ManagerOverview';
import { ProductManagement } from './ProductManagement';
import { InventoryManagement } from './InventoryManagement';
import { ProductFormModal } from './ProductFormModal';
import { ProductImageModal } from './ProductImageModal';
import { StockAdjustmentModal } from './StockAdjustmentModal';
import { InventoryHistoryModal } from './InventoryHistoryModal';
import { Toast } from '../Toast';

interface ManagerDashboardProps {
  stores: StoreType[];
  onReturnToStorefront: () => void;
  onNavigateToAdmin?: () => void;
}

export const ManagerDashboard: React.FC<ManagerDashboardProps> = ({
  stores,
  onReturnToStorefront,
  onNavigateToAdmin,
}) => {
  const { user, isAuthenticated, login, promptAuth } = useAuth();
  const [currentTab, setCurrentTab] = useState<ManagerTab>('overview');

  // Selected store state (defaults to manager's assigned store, or admin selection / first store)
  const [adminSelectedStore, setAdminSelectedStore] = useState<StoreType | null>(null);

  const selectedStore = useMemo<StoreType | null>(() => {
    if (user?.role === 'STORE_MANAGER' && user.assigned_store_id) {
      return stores.find((s) => s.id === user.assigned_store_id) || null;
    }
    if (adminSelectedStore) {
      return adminSelectedStore;
    }
    return stores.length > 0 ? stores[0] : null;
  }, [user, stores, adminSelectedStore]);

  // Data state
  const [products, setProducts] = useState<ManagerProduct[]>([]);
  const [inventory, setInventory] = useState<StockResponse[]>([]);
  const [lowStockItems, setLowStockItems] = useState<StockResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Active modal targets
  const [formModalOpen, setFormModalOpen] = useState<boolean>(false);
  const [productToEdit, setProductToEdit] = useState<ManagerProduct | null>(null);

  const [imageModalOpen, setImageModalOpen] = useState<boolean>(false);
  const [imageModalProduct, setImageModalProduct] = useState<ManagerProduct | null>(null);

  const [adjustModalOpen, setAdjustModalOpen] = useState<boolean>(false);
  const [adjustModalProduct, setAdjustModalProduct] = useState<ManagerProduct | null>(null);

  const [historyModalOpen, setHistoryModalOpen] = useState<boolean>(false);
  const [historyModalProduct, setHistoryModalProduct] = useState<ManagerProduct | null>(null);

  const isAuthorized =
    isAuthenticated &&
    user &&
    (user.role === 'STORE_MANAGER' || user.role === 'ADMIN' || user.role === 'SUPER_ADMIN');

  // Load manager catalogue and inventory data
  const loadDashboardData = useCallback(async () => {
    if (!isAuthorized) return;

    setLoading(true);
    setError(null);

    const storeId = selectedStore?.id;
    try {
      const [prodList, invList, lowList] = await Promise.all([
        fetchManagerProducts({ storeId, limit: 100 }),
        fetchStoreInventory(storeId, 0, 200),
        fetchLowStockInventory(storeId),
      ]);

      setProducts(prodList);
      setInventory(invList);
      setLowStockItems(lowList);
    } catch (err: unknown) {
      console.error('Failed to load manager dashboard data:', err);
      setError(err instanceof Error ? err.message : 'Error retrieving dashboard data');
    } finally {
      setLoading(false);
    }
  }, [isAuthorized, selectedStore?.id]);

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      if (!ignore) {
        await loadDashboardData();
      }
    };
    run();
    return () => {
      ignore = true;
    };
  }, [loadDashboardData]);

  // Handlers
  const handleOpenAddProduct = () => {
    setProductToEdit(null);
    setFormModalOpen(true);
  };

  const handleOpenEditProduct = (prod: ManagerProduct) => {
    setProductToEdit(prod);
    setFormModalOpen(true);
  };

  const handleOpenImageModal = (prod: ManagerProduct) => {
    setImageModalProduct(prod);
    setImageModalOpen(true);
  };

  const handleOpenAdjustModal = (prod: ManagerProduct) => {
    setAdjustModalProduct(prod);
    setAdjustModalOpen(true);
  };

  const handleOpenHistoryModal = (prod: ManagerProduct) => {
    setHistoryModalProduct(prod);
    setHistoryModalOpen(true);
  };

  const handleDeactivate = async (prod: ManagerProduct) => {
    const confirm = window.confirm(
      `Are you sure you want to safely deactivate "${prod.name}" (${prod.sku})? It will be hidden from customer storefront but preserved for order audit records.`
    );
    if (!confirm) return;

    try {
      await deactivateManagerProduct(prod.id, selectedStore?.id);
      setToastMessage(`Deactivated product "${prod.name}"`);
      await loadDashboardData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to deactivate product');
    }
  };

  const handleQuickManagerLogin = async () => {
    try {
      await login({ email: 'manager.bengaluru@smartcart.in', password: 'Demo@123' });
      setToastMessage('Signed in as Bengaluru Store Manager');
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Login failed');
    }
  };

  // =========================================================================
  // VIEW: Access Restricted Gate
  // =========================================================================
  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-slate-900 text-white flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-800 rounded-3xl p-8 border border-slate-700 shadow-2xl text-center space-y-5 animate-fade-in">
          <div className="w-16 h-16 rounded-2xl bg-amber-500/20 text-amber-400 flex items-center justify-center mx-auto border border-amber-500/30">
            <Lock className="w-8 h-8" />
          </div>

          <div>
            <span className="px-3 py-1 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 uppercase tracking-wider border border-amber-500/30">
              Role Authorization Required
            </span>
            <h2 className="text-2xl font-black tracking-tight mt-2 text-white">
              Store Manager Portal
            </h2>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              This dashboard is strictly restricted to authenticated{' '}
              <strong className="text-slate-200">STORE_MANAGER</strong> and{' '}
              <strong className="text-slate-200">ADMIN</strong> accounts.
              {user?.role === 'CUSTOMER' && (
                <span className="block mt-2 text-amber-300">
                  You are currently logged in as a <strong>CUSTOMER</strong>. Please switch to a manager account.
                </span>
              )}
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <button
              type="button"
              onClick={handleQuickManagerLogin}
              className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-lg transition flex items-center justify-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              <span>Instant Login as Bengaluru Store Manager</span>
            </button>

            <button
              type="button"
              onClick={() => promptAuth('Sign in with authorized STORE_MANAGER or ADMIN credentials')}
              className="w-full py-2.5 px-4 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 font-semibold text-xs transition"
            >
              Enter Custom Manager Credentials
            </button>

            <button
              type="button"
              onClick={onReturnToStorefront}
              className="w-full py-2 px-4 rounded-xl text-slate-400 hover:text-white font-semibold text-xs transition flex items-center justify-center gap-1.5"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Return to Customer Storefront</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // VIEW: Authorized Store Manager Dashboard
  // =========================================================================
  return (
    <ManagerLayout
      currentTab={currentTab}
      onTabChange={setCurrentTab}
      stores={stores}
      selectedStore={selectedStore}
      onSelectStore={setAdminSelectedStore}
      onReturnToStorefront={onReturnToStorefront}
      onNavigateToAdmin={onNavigateToAdmin}
    >
      {toastMessage && (
        <Toast message={toastMessage} onClose={() => setToastMessage(null)} />
      )}

      {loading ? (
        <div className="py-24 flex flex-col items-center justify-center text-gray-400 gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-600" />
          <span className="text-xs font-semibold">Loading store catalogue & inventory records...</span>
        </div>
      ) : error ? (
        <div className="p-6 rounded-2xl bg-red-50 border border-red-200 text-center space-y-3">
          <ShieldAlert className="w-8 h-8 text-red-500 mx-auto" />
          <h3 className="text-sm font-bold text-red-900">Failed to load store data</h3>
          <p className="text-xs text-red-700">{error}</p>
          <button
            type="button"
            onClick={loadDashboardData}
            className="px-4 py-2 rounded-xl bg-red-600 text-white font-bold text-xs"
          >
            Retry Connection
          </button>
        </div>
      ) : (
        <div>
          {currentTab === 'overview' && (
            <ManagerOverview
              products={products}
              inventory={inventory}
              lowStockItems={lowStockItems}
              store={selectedStore}
              onOpenAdjustModal={handleOpenAdjustModal}
              onNavigateToProducts={() => setCurrentTab('products')}
              onNavigateToInventory={() => setCurrentTab('inventory')}
              onOpenAddProduct={handleOpenAddProduct}
            />
          )}

          {currentTab === 'products' && (
            <ProductManagement
              products={products}
              onOpenAddModal={handleOpenAddProduct}
              onOpenEditModal={handleOpenEditProduct}
              onOpenImageModal={handleOpenImageModal}
              onDeactivateProduct={handleDeactivate}
              onRefresh={loadDashboardData}
              isAdmin={user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN'}
            />
          )}

          {currentTab === 'inventory' && (
            <InventoryManagement
              products={products}
              inventory={inventory}
              onOpenAdjustModal={handleOpenAdjustModal}
              onOpenHistoryModal={handleOpenHistoryModal}
              onRefresh={loadDashboardData}
            />
          )}

          {currentTab === 'alerts' && (
            <InventoryManagement
              products={products}
              inventory={lowStockItems}
              onOpenAdjustModal={handleOpenAdjustModal}
              onOpenHistoryModal={handleOpenHistoryModal}
              onRefresh={loadDashboardData}
            />
          )}
        </div>
      )}

      {/* Product Form Modal (Create / Edit) */}
      <ProductFormModal
        isOpen={formModalOpen}
        onClose={() => setFormModalOpen(false)}
        onSuccess={() => {
          setToastMessage(productToEdit ? 'Product updated successfully' : 'Product created successfully');
          loadDashboardData();
        }}
        productToEdit={productToEdit}
        storeId={selectedStore?.id}
        isAdmin={user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN'}
      />

      {/* Product Image Modal (Cloudinary Upload / Delete) */}
      <ProductImageModal
        isOpen={imageModalOpen}
        onClose={() => setImageModalOpen(false)}
        onSuccess={() => {
          setToastMessage('Product image updated');
          loadDashboardData();
        }}
        product={imageModalProduct}
        storeId={selectedStore?.id}
      />

      {/* Stock Adjustment Modal */}
      <StockAdjustmentModal
        isOpen={adjustModalOpen}
        onClose={() => setAdjustModalOpen(false)}
        onSuccess={() => {
          setToastMessage('Stock adjustment completed and audited in PostgreSQL');
          loadDashboardData();
        }}
        product={adjustModalProduct}
        storeId={selectedStore?.id}
      />

      {/* Inventory Audit History Modal */}
      <InventoryHistoryModal
        isOpen={historyModalOpen}
        onClose={() => setHistoryModalOpen(false)}
        product={historyModalProduct}
        storeId={selectedStore?.id}
      />
    </ManagerLayout>
  );
};
