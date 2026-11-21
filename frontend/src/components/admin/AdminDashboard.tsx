import React, { useState, useEffect, useCallback } from 'react';
import {
  Loader2,
  Lock,
  ArrowLeft,
  Sparkles,
  ShieldAlert,
} from 'lucide-react';
import type {
  Store,
  ManagerProduct,
  OrderResponse,
  SystemHealthResponse,
  DatabaseHealthResponse,
} from '../../types';
import {
  fetchStoresAdmin,
  fetchManagerProducts,
  fetchOrders,
  fetchSystemHealth,
  fetchDatabaseHealth,
  deactivateManagerProduct,
} from '../../api/client';
import { useAuth } from '../../context/useAuth';
import { AdminLayout, type AdminTab } from './AdminLayout';
import { AdminOverview } from './AdminOverview';
import { StoreManagement } from './StoreManagement';
import { GlobalCatalogue } from './GlobalCatalogue';
import { OrderManagement } from './OrderManagement';
import { UserStaffManagement } from './UserStaffManagement';
import { SystemHealthPanel } from './SystemHealthPanel';
import { ProductFormModal } from '../manager/ProductFormModal';
import { ProductImageModal } from '../manager/ProductImageModal';
import { Toast } from '../Toast';

interface AdminDashboardProps {
  stores: Store[];
  onReturnToStorefront: () => void;
  onNavigateToManager: () => void;
}

export const AdminDashboard: React.FC<AdminDashboardProps> = ({
  stores: initialStores,
  onReturnToStorefront,
  onNavigateToManager,
}) => {
  const { user, isAuthenticated, login, promptAuth } = useAuth();
  const [currentTab, setCurrentTab] = useState<AdminTab>('overview');

  // Selected Store Context (null = Global Network All Stores)
  const [selectedStore, setSelectedStore] = useState<Store | null>(null);

  // Data states
  const [stores, setStores] = useState<Store[]>(initialStores);
  const [products, setProducts] = useState<ManagerProduct[]>([]);
  const [orders, setOrders] = useState<OrderResponse[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealthResponse | null>(null);
  const [dbHealth, setDbHealth] = useState<DatabaseHealthResponse | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Modals
  const [formModalOpen, setFormModalOpen] = useState(false);
  const [productToEdit, setProductToEdit] = useState<ManagerProduct | null>(null);

  const [imageModalOpen, setImageModalOpen] = useState(false);
  const [imageModalProduct, setImageModalProduct] = useState<ManagerProduct | null>(null);

  const isAuthorized =
    isAuthenticated &&
    user &&
    (user.role === 'ADMIN' || user.role === 'SUPER_ADMIN');

  // Load Administrator Data
  const loadAdminData = useCallback(async () => {
    if (!isAuthorized) return;

    setLoading(true);
    setError(null);

    const storeId = selectedStore?.id;
    try {
      // For orders, if storeId is not set, use first store id for orders endpoint
      const effectiveStoreIdForOrders = storeId || (stores.length > 0 ? stores[0].id : undefined);

      const [storeList, prodList, orderList, sysHealth, databaseHealth] = await Promise.all([
        fetchStoresAdmin({ limit: 100 }),
        fetchManagerProducts({ storeId, limit: 100 }),
        effectiveStoreIdForOrders ? fetchOrders({ storeId: effectiveStoreIdForOrders, limit: 50 }) : Promise.resolve([]),
        fetchSystemHealth().catch(() => null),
        fetchDatabaseHealth().catch(() => null),
      ]);

      if (storeList && storeList.length > 0) setStores(storeList);
      setProducts(prodList);
      setOrders(orderList);
      if (sysHealth) setSystemHealth(sysHealth);
      if (databaseHealth) setDbHealth(databaseHealth);
    } catch (err: unknown) {
      console.error('Failed to load admin data:', err);
      setError(err instanceof Error ? err.message : 'Error loading admin data');
    } finally {
      setLoading(false);
    }
  }, [isAuthorized, selectedStore?.id, stores]);

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      if (!ignore) {
        await loadAdminData();
      }
    };
    run();
    return () => {
      ignore = true;
    };
  }, [loadAdminData]);

  // Product Actions
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

  const handleDeactivateProduct = async (prod: ManagerProduct) => {
    const confirm = window.confirm(
      `Administrator Confirmation: Deactivate "${prod.name}" (${prod.sku})? It will be removed from customer searches but preserved in order logs.`
    );
    if (!confirm) return;

    try {
      await deactivateManagerProduct(prod.id, selectedStore?.id);
      setToastMessage(`Deactivated product "${prod.name}"`);
      await loadAdminData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to deactivate product');
    }
  };

  const handleQuickAdminLogin = async () => {
    try {
      await login({ email: 'admin@smartcart.in', password: 'Demo@123' });
      setToastMessage('Authenticated as System Administrator');
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Admin login failed');
    }
  };

  // =========================================================================
  // VIEW: Authorization Gate
  // =========================================================================
  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-900 rounded-3xl p-8 border border-slate-800 shadow-2xl text-center space-y-5 animate-fade-in">
          <div className="w-16 h-16 rounded-2xl bg-purple-500/20 text-purple-400 flex items-center justify-center mx-auto border border-purple-500/30">
            <Lock className="w-8 h-8" />
          </div>

          <div>
            <span className="px-3 py-1 rounded-full text-[10px] font-bold bg-purple-500/20 text-purple-300 uppercase tracking-wider border border-purple-500/30">
              Administrator Privileges Required
            </span>
            <h2 className="text-2xl font-black tracking-tight mt-2 text-white">
              Admin Governance Console
            </h2>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              This portal provides central governance for product pricing, store network management, user roles, and order auditing across India. Access is restricted to <strong className="text-slate-200">ADMIN</strong> accounts.
            </p>
          </div>

          <div className="space-y-3 pt-2">
            <button
              type="button"
              onClick={handleQuickAdminLogin}
              className="w-full py-3 px-4 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-lg shadow-purple-600/30 transition flex items-center justify-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              <span>Instant Login as Administrator (admin@smartcart.in)</span>
            </button>

            <button
              type="button"
              onClick={() => promptAuth('Sign in with authorized ADMIN or SUPER_ADMIN credentials')}
              className="w-full py-2.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs transition"
            >
              Enter Custom Admin Credentials
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
  // VIEW: Authorized Administrator Console
  // =========================================================================
  return (
    <AdminLayout
      currentTab={currentTab}
      onTabChange={setCurrentTab}
      stores={stores}
      selectedStore={selectedStore}
      onSelectStore={setSelectedStore}
      onReturnToStorefront={onReturnToStorefront}
      onNavigateToManager={onNavigateToManager}
    >
      {toastMessage && (
        <Toast message={toastMessage} onClose={() => setToastMessage(null)} />
      )}

      {loading ? (
        <div className="py-24 flex flex-col items-center justify-center text-slate-400 gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
          <span className="text-xs font-semibold">Loading multi-store governance telemetry...</span>
        </div>
      ) : error ? (
        <div className="p-6 rounded-3xl bg-rose-500/10 border border-rose-500/20 text-center space-y-3">
          <ShieldAlert className="w-8 h-8 text-rose-400 mx-auto" />
          <h3 className="text-sm font-bold text-rose-200">Failed to load system data</h3>
          <p className="text-xs text-rose-400">{error}</p>
          <button
            type="button"
            onClick={loadAdminData}
            className="px-4 py-2 rounded-xl bg-rose-600 text-white font-bold text-xs"
          >
            Retry Connection
          </button>
        </div>
      ) : (
        <div>
          {currentTab === 'overview' && (
            <AdminOverview
              stores={stores}
              products={products}
              orders={orders}
              dbHealth={dbHealth}
              onNavigateTab={(tab) => setCurrentTab(tab)}
              onOpenOrderModal={() => setCurrentTab('orders')}
              onOpenAddProductModal={handleOpenAddProduct}
            />
          )}

          {currentTab === 'stores' && (
            <StoreManagement
              stores={stores}
              onSelectStoreContext={setSelectedStore}
              onNavigateToManager={onNavigateToManager}
            />
          )}

          {currentTab === 'catalogue' && (
            <GlobalCatalogue
              products={products}
              selectedStore={selectedStore}
              onOpenAddModal={handleOpenAddProduct}
              onOpenEditModal={handleOpenEditProduct}
              onOpenImageModal={handleOpenImageModal}
              onDeactivateProduct={handleDeactivateProduct}
              onRefresh={loadAdminData}
            />
          )}

          {currentTab === 'orders' && (
            <OrderManagement
              orders={orders}
              stores={stores}
              selectedStore={selectedStore}
              onRefresh={loadAdminData}
            />
          )}

          {currentTab === 'users' && <UserStaffManagement stores={stores} />}

          {currentTab === 'health' && (
            <SystemHealthPanel
              systemHealth={systemHealth}
              dbHealth={dbHealth}
              onRefresh={loadAdminData}
            />
          )}
        </div>
      )}

      {/* Global Product Create / Edit Modal (Price modification enabled for Admin) */}
      <ProductFormModal
        isOpen={formModalOpen}
        onClose={() => setFormModalOpen(false)}
        onSuccess={() => {
          setToastMessage(productToEdit ? 'Product updated with new price' : 'Product added to global catalogue');
          loadAdminData();
        }}
        productToEdit={productToEdit}
        storeId={selectedStore?.id}
        isAdmin={true}
      />

      {/* Product Image Modal (Cloudinary Upload / Removal) */}
      <ProductImageModal
        isOpen={imageModalOpen}
        onClose={() => setImageModalOpen(false)}
        onSuccess={() => {
          setToastMessage('Product photograph updated on Cloudinary CDN');
          loadAdminData();
        }}
        product={imageModalProduct}
        storeId={selectedStore?.id}
      />
    </AdminLayout>
  );
};
