import React, { useState } from 'react';
import {
  Shield,
  LayoutDashboard,
  Store as StoreIcon,
  Package,
  ClipboardList,
  Users,
  Activity,
  ArrowLeft,
  LogOut,
  ChevronDown,
  Globe,
  Layers,
} from 'lucide-react';
import type { Store } from '../../types';
import { useAuth } from '../../context/useAuth';

export type AdminTab = 'overview' | 'stores' | 'catalogue' | 'orders' | 'users' | 'health';

interface AdminLayoutProps {
  currentTab: AdminTab;
  onTabChange: (tab: AdminTab) => void;
  stores: Store[];
  selectedStore: Store | null;
  onSelectStore: (store: Store | null) => void;
  onReturnToStorefront: () => void;
  onNavigateToManager: () => void;
  children: React.ReactNode;
}

export const AdminLayout: React.FC<AdminLayoutProps> = ({
  currentTab,
  onTabChange,
  stores,
  selectedStore,
  onSelectStore,
  onReturnToStorefront,
  onNavigateToManager,
  children,
}) => {
  const { user, logout } = useAuth();
  const [storeMenuOpen, setStoreMenuOpen] = useState(false);

  const navItems: { id: AdminTab; label: string; icon: React.ElementType }[] = [
    { id: 'overview', label: 'Network Overview', icon: LayoutDashboard },
    { id: 'stores', label: 'Stores Network', icon: StoreIcon },
    { id: 'catalogue', label: 'Global Catalogue', icon: Package },
    { id: 'orders', label: 'Orders & Fulfillment', icon: ClipboardList },
    { id: 'users', label: 'Staff & Roles', icon: Users },
    { id: 'health', label: 'Cloud Infrastructure', icon: Activity },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-purple-600 selection:text-white">
      {/* Top Header Bar */}
      <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16 sm:h-20 gap-4">
            {/* Branding */}
            <div className="flex items-center space-x-3 shrink-0">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 via-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-lg shadow-purple-500/30 ring-2 ring-purple-500/40 font-black text-xl">
                <Shield className="w-5 h-5 text-purple-100" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-extrabold text-lg sm:text-xl tracking-tight text-white">
                    Smart<span className="text-purple-400">Cart</span>
                  </span>
                  <span className="text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    Admin Console
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 hidden sm:block">
                  Central Governance • Multi-Store Architecture
                </p>
              </div>
            </div>

            {/* Scope / Global Store Context Dropdown */}
            <div className="relative shrink-0">
              <button
                type="button"
                onClick={() => setStoreMenuOpen(!storeMenuOpen)}
                className="flex items-center space-x-2.5 px-3.5 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-800 border border-slate-700/80 text-xs sm:text-sm font-semibold transition"
              >
                <Globe className="w-4 h-4 text-purple-400" />
                <span className="max-w-[160px] truncate">
                  {selectedStore ? selectedStore.name : 'All Stores (Global Network)'}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              {storeMenuOpen && (
                <div className="absolute right-0 mt-2 w-72 bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 py-2 z-50 animate-in fade-in slide-in-from-top-1 text-xs">
                  <div className="px-3.5 py-2 border-b border-slate-800 text-[11px] text-slate-400 font-bold uppercase tracking-wider">
                    Select Scope
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      onSelectStore(null);
                      setStoreMenuOpen(false);
                    }}
                    className={`w-full text-left px-3.5 py-2.5 flex items-center justify-between hover:bg-slate-800 transition ${
                      selectedStore === null ? 'bg-purple-900/30 text-purple-300 font-bold' : 'text-slate-300'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <Globe className="w-4 h-4 text-purple-400" />
                      <span>All Stores (Global Network)</span>
                    </div>
                  </button>
                  <div className="max-h-56 overflow-y-auto divide-y divide-slate-800/60">
                    {stores.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => {
                          onSelectStore(s);
                          setStoreMenuOpen(false);
                        }}
                        className={`w-full text-left px-3.5 py-2 hover:bg-slate-800 transition flex items-center justify-between ${
                          selectedStore?.id === s.id ? 'bg-purple-900/30 text-purple-300 font-bold' : 'text-slate-300'
                        }`}
                      >
                        <div className="min-w-0">
                          <p className="truncate font-semibold">{s.name}</p>
                          <p className="text-[10px] text-slate-500 font-mono">
                            {s.city}, {s.state} • {s.code}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Quick Actions & Profile */}
            <div className="flex items-center space-x-2 sm:space-x-3 shrink-0">
              <button
                type="button"
                onClick={onNavigateToManager}
                className="hidden lg:flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition"
                title="Switch to Store Manager Portal"
              >
                <Layers className="w-3.5 h-3.5 text-emerald-400" />
                <span>Manager Portal</span>
              </button>

              <button
                type="button"
                onClick={onReturnToStorefront}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition"
                title="Return to Customer Storefront"
              >
                <ArrowLeft className="w-3.5 h-3.5 text-purple-400" />
                <span className="hidden sm:inline">Storefront</span>
              </button>

              {/* Profile Pill */}
              <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
                <div className="text-right hidden md:block">
                  <p className="text-xs font-bold text-slate-200 truncate max-w-32">
                    {user?.full_name || 'Administrator'}
                  </p>
                  <p className="text-[10px] text-purple-400 font-mono uppercase tracking-wider">
                    {user?.role || 'ADMIN'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  className="p-2 rounded-xl text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition"
                  title="Sign Out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Horizontal Navigation Tabs */}
        <div className="border-t border-slate-800/80 bg-slate-900/60">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <nav className="flex space-x-1 sm:space-x-2 overflow-x-auto py-2 scrollbar-none">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = currentTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onTabChange(item.id)}
                    className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold whitespace-nowrap transition-all ${
                      isActive
                        ? 'bg-purple-600 text-white shadow-md shadow-purple-600/30'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </nav>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {children}
      </main>

      {/* Global Admin Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-6 text-slate-500 text-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>SmartCart 2.0 Live Cloud Services: Aiven PostgreSQL • Kafka • OpenSearch</span>
          </div>
          <div className="flex items-center gap-4 text-[11px]">
            <span>Zero Overselling Guarantee</span>
            <span>•</span>
            <span>10-Minute Hold Lock</span>
            <span>•</span>
            <span>Idempotent Outbox</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
