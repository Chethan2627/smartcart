import React, { useState } from 'react';
import {
  ClipboardList,
  Search,
  CheckCircle2,
  Clock,
  XCircle,
  Truck,
  AlertTriangle,
  RotateCcw,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import type { OrderResponse, OrderStatus, Store } from '../../types';
import { formatPrice } from '../../utils/format';
import { cancelOrderAdmin, fetchOrderDetail } from '../../api/client';

interface OrderManagementProps {
  orders: OrderResponse[];
  stores: Store[];
  selectedStore: Store | null;
  onRefresh: () => void;
}

export const OrderManagement: React.FC<OrderManagementProps> = ({
  orders,
  stores,
  selectedStore,
  onRefresh,
}) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [selectedOrder, setSelectedOrder] = useState<OrderResponse | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelReason, setCancelReason] = useState('Customer requested order cancellation');

  const filteredOrders = orders.filter((o) => {
    const matchesSearch =
      o.order_number.toLowerCase().includes(search.toLowerCase()) ||
      o.customer_id.toLowerCase().includes(search.toLowerCase()) ||
      o.id.toLowerCase().includes(search.toLowerCase());

    const matchesStatus = statusFilter === 'ALL' || o.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const handleInspectOrder = async (orderId: string) => {
    try {
      const fullOrder = await fetchOrderDetail(orderId);
      setSelectedOrder(fullOrder);
    } catch {
      const fallback = orders.find((o) => o.id === orderId);
      if (fallback) setSelectedOrder(fallback);
    }
  };

  const handleCancelOrder = async () => {
    if (!selectedOrder) return;
    const confirm = window.confirm(
      `Are you sure you want to cancel order "${selectedOrder.order_number}"? Reserved stock will be automatically restored to store inventory.`
    );
    if (!confirm) return;

    setCancelling(true);
    try {
      const updated = await cancelOrderAdmin(selectedOrder.id, cancelReason);
      setSelectedOrder(updated);
      onRefresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to cancel order');
    } finally {
      setCancelling(false);
    }
  };

  const getStatusBadge = (status: OrderStatus) => {
    switch (status) {
      case 'CONFIRMED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>CONFIRMED</span>
          </span>
        );
      case 'PENDING':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            <Clock className="w-3 h-3 text-amber-400" />
            <span>PENDING</span>
          </span>
        );
      case 'DELIVERED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
            <Truck className="w-3 h-3 text-blue-400" />
            <span>DELIVERED</span>
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
            <XCircle className="w-3 h-3 text-rose-400" />
            <span>CANCELLED</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-800 text-slate-300">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Orders & Fulfillment Audit
          </h2>
          <p className="text-xs sm:text-sm text-slate-400 mt-1">
            {selectedStore
              ? `Orders fulfilled by ${selectedStore.name}`
              : 'Cross-store order transactions with inventory audit and cancellation recovery'}
          </p>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          className="self-start sm:self-auto px-3.5 py-2 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 text-xs font-semibold flex items-center gap-2 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh Orders</span>
        </button>
      </div>

      {/* Filter Toolbar */}
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3">
        <div className="sm:col-span-8 relative">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by order number (e.g. ORD-), customer UUID, or ID..."
            className="w-full pl-10 pr-4 py-2.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
          />
        </div>

        <div className="sm:col-span-4">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full py-2.5 px-3 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-300 focus:outline-none focus:border-purple-500"
          >
            <option value="ALL">All Order Statuses ({orders.length})</option>
            <option value="PENDING">PENDING</option>
            <option value="CONFIRMED">CONFIRMED</option>
            <option value="PACKED">PACKED</option>
            <option value="SHIPPED">SHIPPED</option>
            <option value="DELIVERED">DELIVERED</option>
            <option value="CANCELLED">CANCELLED</option>
          </select>
        </div>
      </div>

      {/* Orders Table */}
      <div className="bg-slate-900/80 rounded-3xl border border-slate-800/80 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="bg-slate-900/90 border-b border-slate-800 text-[11px] uppercase font-bold text-slate-400 tracking-wider">
              <tr>
                <th className="p-4">Order Number</th>
                <th className="p-4">Fulfillment Store</th>
                <th className="p-4">Total Amount</th>
                <th className="p-4">Items Count</th>
                <th className="p-4">Order Status</th>
                <th className="p-4">Placed At</th>
                <th className="p-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {filteredOrders.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-12 text-center text-slate-500">
                    <ClipboardList className="w-8 h-8 mx-auto mb-2 opacity-30 text-slate-400" />
                    <p className="font-semibold text-slate-400">No orders match filter criteria</p>
                    <p className="text-[11px] text-slate-500 mt-1">
                      New checkouts from customers will be listed here automatically.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredOrders.map((order) => {
                  const storeMatch = stores.find((s) => s.id === order.store_id);
                  const storeName = storeMatch ? storeMatch.name : 'Store ' + order.store_id.slice(0, 8);
                  const formattedDate = new Date(order.created_at).toLocaleString('en-IN', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  });

                  return (
                    <tr key={order.id} className="hover:bg-slate-800/40 transition">
                      {/* Order Number */}
                      <td className="p-4">
                        <span className="font-mono font-bold text-white text-sm">
                          {order.order_number}
                        </span>
                        <p className="text-[10px] text-slate-500 font-mono">
                          ID: {order.id.slice(0, 8)}...
                        </p>
                      </td>

                      {/* Store */}
                      <td className="p-4">
                        <p className="font-semibold text-slate-200">{storeName}</p>
                        <p className="text-[10px] text-slate-400 font-mono">
                          Store: {storeMatch?.code || 'NODE'}
                        </p>
                      </td>

                      {/* Total */}
                      <td className="p-4">
                        <span className="font-extrabold text-white text-sm">
                          {formatPrice(order.total_paise)}
                        </span>
                      </td>

                      {/* Items */}
                      <td className="p-4">
                        <span className="text-slate-300 font-semibold">
                          {order.items.length} {order.items.length === 1 ? 'item' : 'items'}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="p-4">{getStatusBadge(order.status)}</td>

                      {/* Date */}
                      <td className="p-4 text-slate-400 font-mono text-[11px]">
                        {formattedDate}
                      </td>

                      {/* Action */}
                      <td className="p-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleInspectOrder(order.id)}
                          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-purple-300 hover:text-white text-xs font-semibold transition"
                        >
                          Inspect Order
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Order Details & Audit Modal */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in overflow-y-auto">
          <div
            className="relative w-full max-w-2xl bg-slate-900 rounded-3xl border border-slate-800 p-6 space-y-6 shadow-2xl my-8"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono font-extrabold text-lg text-white">
                    {selectedOrder.order_number}
                  </span>
                  {getStatusBadge(selectedOrder.status)}
                </div>
                <p className="text-xs text-slate-400 mt-1 font-mono">
                  Order UUID: {selectedOrder.id}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Overview Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Total Value</span>
                <p className="font-extrabold text-white text-sm mt-0.5">{formatPrice(selectedOrder.total_paise)}</p>
              </div>
              <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Store Node</span>
                <p className="font-bold text-slate-200 truncate mt-0.5">
                  {stores.find((s) => s.id === selectedOrder.store_id)?.name || 'Assigned Store'}
                </p>
              </div>
              <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Customer ID</span>
                <p className="font-mono text-purple-300 truncate mt-0.5">{selectedOrder.customer_id.slice(0, 10)}...</p>
              </div>
              <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-800">
                <span className="text-[10px] text-slate-500 uppercase font-semibold">Order Placed</span>
                <p className="text-slate-300 mt-0.5 text-[11px] font-mono">
                  {new Date(selectedOrder.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
            </div>

            {/* Line Items */}
            <div className="space-y-2">
              <span className="text-xs font-bold text-slate-300">Ordered Line Items ({selectedOrder.items.length})</span>
              <div className="divide-y divide-slate-800 rounded-2xl border border-slate-800 overflow-hidden bg-slate-950/40">
                {selectedOrder.items.map((item, idx) => (
                  <div key={idx} className="p-3 flex items-center justify-between text-xs">
                    <div>
                      <p className="font-mono text-slate-300 text-xs font-semibold">
                        Product: {item.product_id}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        Qty: {item.qty} × {formatPrice(item.unit_price_paise)}
                      </p>
                    </div>
                    <span className="font-bold text-white">
                      {formatPrice((item.item_subtotal_paise || (item.unit_price_paise * item.qty)))}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Status Transition History */}
            {selectedOrder.status_history && selectedOrder.status_history.length > 0 && (
              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-300">Status Audit Timeline</span>
                <div className="p-3 rounded-2xl bg-slate-950/40 border border-slate-800 space-y-2">
                  {selectedOrder.status_history.map((hist, idx) => (
                    <div key={idx} className="flex items-center justify-between text-[11px] font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-slate-500">{hist.from_status || 'INIT'}</span>
                        <span className="text-purple-400">→</span>
                        <span className="text-emerald-400 font-bold">{hist.to_status}</span>
                      </div>
                      <span className="text-slate-500">
                        {new Date(hist.changed_at).toLocaleString('en-IN')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Cancellation Controls (Only for eligible active orders) */}
            {selectedOrder.status !== 'CANCELLED' && selectedOrder.status !== 'DELIVERED' && (
              <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 space-y-3">
                <div className="flex items-center gap-2 text-rose-300 font-bold text-xs">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>Administrative Order Cancellation & Stock Restoration</span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Cancelling will execute PostgreSQL <code className="text-purple-300">cancel_order()</code>, restore reserved store inventory, publish an <code className="text-purple-300">order.cancelled</code> outbox event, and update status.
                </p>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    type="text"
                    value={cancelReason}
                    onChange={(e) => setCancelReason(e.target.value)}
                    placeholder="Cancellation audit reason..."
                    className="flex-1 py-1.5 px-3 bg-slate-900 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500"
                  />
                  <button
                    type="button"
                    onClick={handleCancelOrder}
                    disabled={cancelling}
                    className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs transition disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {cancelling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                    <span>Cancel Order</span>
                  </button>
                </div>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setSelectedOrder(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition"
              >
                Close Audit View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
