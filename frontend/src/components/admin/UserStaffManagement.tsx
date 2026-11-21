import React, { useState } from 'react';
import {
  Users,
  Search,
  UserCheck,
  UserX,
  ShieldAlert,
  Building2,
  CheckCircle2,
  Loader2,
  KeyRound,
} from 'lucide-react';
import type { User, Store } from '../../types';
import { useAuth } from '../../context/useAuth';
import { fetchUserById, updateUserStatus, assignStoreManager } from '../../api/client';

interface UserStaffManagementProps {
  stores: Store[];
}

export const UserStaffManagement: React.FC<UserStaffManagementProps> = ({ stores }) => {
  const { user: currentUser } = useAuth();

  const [searchUserId, setSearchUserId] = useState('');
  const [inspectedUser, setInspectedUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Store Manager Assignment state
  const [selectedStoreId, setSelectedStoreId] = useState<string>(
    stores.length > 0 ? stores[0].id : ''
  );
  const [isAssigningManager, setIsAssigningManager] = useState(false);

  // Quick Seed Users Lookup
  const handleLookupUser = async (targetId: string) => {
    if (!targetId.trim()) return;
    setLoading(true);
    setError(null);
    setActionSuccess(null);
    try {
      const user = await fetchUserById(targetId.trim());
      setInspectedUser(user);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'User not found or lookup failed');
      setInspectedUser(null);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (isActive: boolean) => {
    if (!inspectedUser) return;
    if (inspectedUser.id === currentUser?.id && !isActive) {
      setError('Safety Protection: Administrators cannot deactivate their own accounts.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const updated = await updateUserStatus(inspectedUser.id, isActive);
      setInspectedUser(updated);
      setActionSuccess(`User account ${isActive ? 'activated' : 'deactivated'} successfully.`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update user status');
    } finally {
      setLoading(false);
    }
  };

  const handleAssignManager = async () => {
    if (!inspectedUser || !selectedStoreId) return;

    setIsAssigningManager(true);
    setError(null);
    setActionSuccess(null);
    try {
      const updated = await assignStoreManager(inspectedUser.id, selectedStoreId);
      setInspectedUser(updated);
      const storeName = stores.find((s) => s.id === selectedStoreId)?.name || 'store';
      setActionSuccess(`User assigned as Store Manager for "${storeName}".`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to assign store manager');
    } finally {
      setIsAssigningManager(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Staff & Role Administration
          </h2>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            Inspect user profiles, manage account active statuses, and assign store managers to fulfillment hubs.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-300 text-xs font-bold flex items-center gap-1.5">
            <KeyRound className="w-3.5 h-3.5" />
            <span>Role-Based Access Control</span>
          </span>
        </div>
      </div>

      {/* Quick Lookup Bar */}
      <div className="p-6 rounded-3xl bg-slate-900/80 border border-slate-800 space-y-4">
        <label className="block text-xs font-bold text-slate-300 uppercase tracking-wider">
          Lookup User by UUID
        </label>
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchUserId}
              onChange={(e) => setSearchUserId(e.target.value)}
              placeholder="Enter User UUID (e.g. 00000000-0000-0000-0000-000000000000)..."
              className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-white placeholder-slate-500 font-mono focus:outline-none focus:border-purple-500"
            />
          </div>
          <button
            type="button"
            onClick={() => handleLookupUser(searchUserId)}
            disabled={loading || !searchUserId.trim()}
            className="px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-md transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            <span>Lookup User</span>
          </button>
        </div>

        {/* Quick Current User & Seed Preset Buttons */}
        {currentUser && (
          <div className="pt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500 text-[11px] font-semibold">Inspect Current User:</span>
            <button
              type="button"
              onClick={() => {
                setSearchUserId(currentUser.id);
                handleLookupUser(currentUser.id);
              }}
              className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-purple-300 font-mono text-[11px] transition"
            >
              Self ({currentUser.full_name})
            </button>
            {currentUser.assigned_store_id && (
              <span className="text-[11px] text-slate-500">
                Bound Store: {stores.find((s) => s.id === currentUser.assigned_store_id)?.name}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Inspected User Profile Details */}
      {inspectedUser ? (
        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white font-bold text-lg shadow-md">
                {inspectedUser.full_name.charAt(0).toUpperCase()}
              </div>
              <div>
                <h3 className="font-bold text-white text-base">{inspectedUser.full_name}</h3>
                <p className="text-xs text-slate-400">{inspectedUser.email}</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                  inspectedUser.role === 'ADMIN' || inspectedUser.role === 'SUPER_ADMIN'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : inspectedUser.role === 'STORE_MANAGER'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                }`}
              >
                {inspectedUser.role}
              </span>

              <span
                className={`px-3 py-1 rounded-full text-xs font-bold ${
                  inspectedUser.is_active
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                }`}
              >
                {inspectedUser.is_active ? 'Active' : 'Deactivated'}
              </span>
            </div>
          </div>

          {/* User Attributes Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="p-3.5 rounded-2xl bg-slate-800/60 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">User UUID</span>
              <p className="font-mono text-purple-300 break-all select-all">{inspectedUser.id}</p>
            </div>

            <div className="p-3.5 rounded-2xl bg-slate-800/60 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Assigned Store</span>
              <p className="font-bold text-slate-200">
                {inspectedUser.assigned_store_id
                  ? stores.find((s) => s.id === inspectedUser.assigned_store_id)?.name || inspectedUser.assigned_store_id
                  : 'No store binding (Global/Customer)'}
              </p>
            </div>

            <div className="p-3.5 rounded-2xl bg-slate-800/60 border border-slate-800 space-y-1">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Account Created</span>
              <p className="font-mono text-slate-300">
                {new Date(inspectedUser.created_at).toLocaleString('en-IN')}
              </p>
            </div>
          </div>

          {/* Admin Management Actions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            {/* Action 1: Status Toggle */}
            <div className="p-4 rounded-2xl bg-slate-800/50 border border-slate-800 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                {inspectedUser.is_active ? (
                  <UserX className="w-4 h-4 text-rose-400" />
                ) : (
                  <UserCheck className="w-4 h-4 text-emerald-400" />
                )}
                <span>Account Active Status</span>
              </div>
              <p className="text-[11px] text-slate-400">
                {inspectedUser.is_active
                  ? 'Deactivating this user will revoke session access immediately.'
                  : 'Re-activate this user account to permit system login.'}
              </p>
              <button
                type="button"
                onClick={() => handleToggleStatus(!inspectedUser.is_active)}
                disabled={loading || (inspectedUser.id === currentUser?.id && inspectedUser.is_active)}
                className={`w-full py-2 px-3 rounded-xl font-bold text-xs transition disabled:opacity-50 ${
                  inspectedUser.is_active
                    ? 'bg-rose-600/30 hover:bg-rose-600 text-rose-200 border border-rose-500/30'
                    : 'bg-emerald-600/30 hover:bg-emerald-600 text-emerald-200 border border-emerald-500/30'
                }`}
              >
                {inspectedUser.is_active ? 'Deactivate User Account' : 'Re-Activate User Account'}
              </button>
            </div>

            {/* Action 2: Store Manager Assignment */}
            <div className="p-4 rounded-2xl bg-slate-800/50 border border-slate-800 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                <Building2 className="w-4 h-4 text-purple-400" />
                <span>Assign Store Manager Role</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Promote this user to STORE_MANAGER and bind them to a designated store.
              </p>
              <div className="flex gap-2">
                <select
                  value={selectedStoreId}
                  onChange={(e) => setSelectedStoreId(e.target.value)}
                  className="flex-1 py-1.5 px-3 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white"
                >
                  {stores.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.code})
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleAssignManager}
                  disabled={isAssigningManager}
                  className="px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition disabled:opacity-50 flex items-center gap-1.5"
                >
                  {isAssigningManager ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                  <span>Assign</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-12 text-center text-slate-500 rounded-3xl bg-slate-900/60 border border-slate-800">
          <Users className="w-10 h-10 mx-auto mb-2 opacity-30 text-purple-400" />
          <p className="font-semibold text-slate-400 text-sm">Enter a User UUID to Inspect Profile</p>
          <p className="text-xs text-slate-500 mt-1">
            Lookup any user to adjust roles, assign stores, or toggle activation status.
          </p>
        </div>
      )}
    </div>
  );
};
