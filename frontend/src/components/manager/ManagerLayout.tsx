import React, { useState } from 'react';
import {
  LayoutDashboard,
  Package,
  Layers,
  AlertTriangle,
  Store,
  ChevronDown,
  LogOut,
  ShoppingBag,
  Menu,
  X,
  Shield,
} from 'lucide-react';
import type { Store as StoreType } from '../../types';
import { useAuth } from '../../context/useAuth';

export type ManagerTab = 'overview' | 'products' | 'inventory' | 'alerts';

interface ManagerLayoutProps {
  currentTab: ManagerTab;
  onTabChange: (tab: ManagerTab) => void;
  stores: StoreType[];
  selectedStore: StoreType | null;
  onSelectStore: (store: StoreType) => void;
  onReturnToStorefront: () => void;
  onNavigateToAdmin?: () => void;
  children: React.ReactNode;
}

export const ManagerLayout: React.FC<ManagerLayoutProps> = ({
  currentTab,
  onTabChange,
  stores,
  selectedStore,
  onSelectStore,
  onReturnToStorefront,
  onNavigateToAdmin,
  children,
}) => {
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [storeSelectOpen, setStoreSelectOpen] = useState(false);

  const isAdmin = user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN';

  const navItems = [
    { id: 'overview', label: 'Dashboard Overview', icon: LayoutDashboard },
    { id: 'products', label: 'Product Catalogue', icon: Package },
    { id: 'inventory', label: 'Store Inventory', icon: Layers },
    { id: 'alerts', label: 'Low Stock Alerts', icon: AlertTriangle },
  ];

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col font-sans text-slate-900">
      {/* Top Navbar */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
          {/* Brand & Mobile Hamburger */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-xl text-gray-500 hover:text-gray-900 hover:bg-gray-100 lg:hidden"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>

            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-600 to-teal-700 flex items-center justify-center text-white shadow-xs">
                <Store className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="font-black text-gray-900 text-base tracking-tight leading-none">
                    SmartCart 2.0
                  </h1>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 uppercase tracking-wider">
                    Manager Portal
                  </span>
                </div>
                <p className="text-[11px] text-gray-500 mt-0.5">Store Operations & Stock Management</p>
              </div>
            </div>
          </div>

          {/* Store Selector (for Admin) or Store Badge (for Store Manager) */}
          <div className="hidden sm:flex items-center gap-2">
            {isAdmin ? (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setStoreSelectOpen(!storeSelectOpen)}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-gray-300 bg-gray-50 hover:bg-white text-xs font-semibold text-gray-800 transition"
                >
                  <Store className="w-4 h-4 text-emerald-600" />
                  <span>Store: {selectedStore?.name || 'Select Store'}</span>
                  <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
                </button>

                {storeSelectOpen && (
                  <div className="absolute left-0 mt-2 w-64 bg-white rounded-xl shadow-xl border border-gray-100 py-1.5 z-50 animate-in fade-in slide-in-from-top-1 text-xs">
                    <div className="px-3 py-1.5 text-[10px] font-bold text-gray-400 uppercase tracking-wider border-b border-gray-100">
                      Multi-Store Administrator Switcher
                    </div>
                    {stores.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => {
                          onSelectStore(s);
                          setStoreSelectOpen(false);
                        }}
                        className={`w-full text-left px-3.5 py-2 flex items-center justify-between hover:bg-emerald-50 transition ${
                          selectedStore?.id === s.id ? 'bg-emerald-50/70 font-bold text-emerald-900' : 'text-gray-700'
                        }`}
                      >
                        <div>
                          <p className="font-semibold">{s.name}</p>
                          <p className="text-[10px] text-gray-400">{s.city}, {s.code}</p>
                        </div>
                        {selectedStore?.id === s.id && (
                          <span className="w-2 h-2 rounded-full bg-emerald-600" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-semibold text-emerald-900">
                <Store className="w-4 h-4 text-emerald-600" />
                <span>{selectedStore?.name || 'SmartCart Bengaluru'}</span>
              </div>
            )}
          </div>

          {/* Right Actions: Return to Storefront & Manager Profile */}
          <div className="flex items-center gap-2 sm:gap-3">
            {isAdmin && onNavigateToAdmin && (
              <button
                type="button"
                onClick={onNavigateToAdmin}
                className="px-3 py-2 rounded-xl bg-purple-900 hover:bg-purple-800 text-purple-200 text-xs font-bold transition flex items-center gap-1.5 shadow-xs"
                title="Switch to Admin Console"
              >
                <Shield className="w-3.5 h-3.5 text-purple-300" />
                <span className="hidden sm:inline">Admin Console</span>
              </button>
            )}

            <button
              type="button"
              onClick={onReturnToStorefront}
              className="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-bold transition flex items-center gap-1.5"
            >
              <ShoppingBag className="w-4 h-4 text-emerald-600" />
              <span className="hidden sm:inline">Customer Storefront</span>
            </button>

            {/* User Pill */}
            <div className="flex items-center gap-2 pl-2 sm:border-l border-gray-200">
              <div className="hidden md:block text-right">
                <span className="text-xs font-bold text-gray-900 block truncate max-w-32">
                  {user?.full_name || 'Store Manager'}
                </span>
                <span className="text-[10px] text-emerald-700 font-semibold block">
                  {user?.role}
                </span>
              </div>

              <button
                type="button"
                onClick={logout}
                className="p-2 rounded-xl text-gray-400 hover:text-red-600 hover:bg-red-50 transition"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Layout Container */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 w-full flex flex-col lg:flex-row gap-6">
        {/* Sidebar Navigation (Desktop) */}
        <aside className="hidden lg:block w-60 shrink-0 space-y-4">
          <div className="p-3 bg-white rounded-2xl border border-gray-200/90 shadow-xs space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = currentTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onTabChange(item.id as ManagerTab)}
                  className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-bold transition ${
                    isActive
                      ? 'bg-emerald-600 text-white shadow-xs'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-gray-400'}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          {/* Operational Guarantees Badge */}
          <div className="p-4 bg-emerald-50/70 rounded-2xl border border-emerald-100 text-xs text-emerald-900 space-y-2">
            <div className="flex items-center gap-1.5 font-bold text-emerald-800">
              <Shield className="w-4 h-4 text-emerald-600" />
              <span>Aiven Cloud Guarantees</span>
            </div>
            <p className="text-[11px] text-emerald-700 leading-relaxed">
              Stock balance changes invoke PostgreSQL row locks and emit transactional outbox events to Aiven Kafka.
            </p>
          </div>
        </aside>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="lg:hidden fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex">
            <div className="w-64 bg-white p-5 flex flex-col justify-between shadow-2xl animate-in slide-in-from-left duration-200">
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-gray-100">
                  <span className="font-bold text-sm text-gray-900">Dashboard Menu</span>
                  <button onClick={() => setMobileMenuOpen(false)} className="p-1 text-gray-400">
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <div className="space-y-1">
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = currentTab === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          onTabChange(item.id as ManagerTab);
                          setMobileMenuOpen(false);
                        }}
                        className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-bold transition ${
                          isActive
                            ? 'bg-emerald-600 text-white shadow-xs'
                            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                        }`}
                      >
                        <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-gray-400'}`} />
                        <span>{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <button
                type="button"
                onClick={onReturnToStorefront}
                className="w-full py-2.5 px-3 rounded-xl bg-gray-100 text-gray-800 font-bold text-xs flex items-center justify-center gap-2"
              >
                <ShoppingBag className="w-4 h-4 text-emerald-600" />
                <span>Customer Storefront</span>
              </button>
            </div>
          </div>
        )}

        {/* Main Content Area */}
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
};
