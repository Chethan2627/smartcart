/**
 * SmartCart 2.0 - Centralized API Service Client
 * Uses environment variable VITE_API_BASE_URL (or fallback VITE_API_URL), falling back to empty string for Vite proxy.
 */

import type {
  Product,
  ProductSearchResponse,
  SearchSuggestionsResponse,
  Store,
  StoreFiltersResponse,
  StockResponse,
  SortOption,
  User,
  CustomerProfile,
  TokenResponse,
  LoginPayload,
  RegisterPayload,
  CartResponse,
  CartItemAddPayload,
  CartItemUpdatePayload,
  OrderResponse,
  OrderStatus,
  CheckoutPayload,
  ManagerProduct,
  ProductCreateManagerPayload,
  ProductUpdateManagerPayload,
  StockAdjustmentPayload,
  StockAdjustmentResponse,
  InventoryAuditLog,
  DatabaseHealthResponse,
} from '../types';

export interface SystemHealthResponse {
  status: string;
  environment: string;
  version: string;
  services: {
    postgresql_configured: boolean;
    kafka_configured: boolean;
    opensearch_configured: boolean;
  };
  timestamp: string;
}

export interface RootResponse {
  project: string;
  tagline: string;
  team: string;
  institution: string;
  status: string;
  docs_url: string;
  timestamp: string;
}

const rawBaseUrl = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '';
export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, '');

export function getApiBaseUrl(): string {
  return API_BASE_URL || '(Vite /api proxy)';
}

const TOKEN_STORAGE_KEY = 'smartcart_auth_token';

let authToken: string | null = null;
if (typeof window !== 'undefined') {
  authToken = localStorage.getItem(TOKEN_STORAGE_KEY);
}

type AuthExpiredCallback = () => void;
const authExpiredCallbacks: Set<AuthExpiredCallback> = new Set();

export function getAuthToken(): string | null {
  return authToken;
}

export function setAuthToken(token: string | null): void {
  authToken = token;
  if (typeof window !== 'undefined') {
    if (token) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  }
}

export function clearAuthToken(): void {
  setAuthToken(null);
}

export function onAuthExpired(cb: AuthExpiredCallback): () => void {
  authExpiredCallbacks.add(cb);
  return () => {
    authExpiredCallbacks.delete(cb);
  };
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const customHeaders = (options.headers as Record<string, string>) || {};
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;

  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...customHeaders,
  };

  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    if (response.status === 401) {
      clearAuthToken();
      authExpiredCallbacks.forEach((cb) => {
        try {
          cb();
        } catch (e) {
          console.error(e);
        }
      });
    }

    let errorDetail = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

/**
 * Fetch list of active fulfillment stores.
 */
export async function fetchStores(): Promise<Store[]> {
  return request<Store[]>('/api/v1/stores?limit=50&is_active=true');
}

/**
 * Fetch catalogue products from PostgreSQL directly.
 */
export async function fetchProducts(options?: {
  category?: string;
  brand?: string;
  skip?: number;
  limit?: number;
}): Promise<Product[]> {
  const query = new URLSearchParams();
  if (options?.category) query.append('category', options.category);
  if (options?.brand) query.append('brand', options.brand);
  if (options?.skip !== undefined) query.append('skip', String(options.skip));
  if (options?.limit !== undefined) query.append('limit', String(options.limit));

  const qs = query.toString();
  return request<Product[]>(`/api/v1/products${qs ? `?${qs}` : ''}`);
}

/**
 * Search products with OpenSearch, scoped to a store.
 */
export async function searchProducts(options: {
  storeId: string;
  q?: string;
  category?: string;
  brand?: string;
  minPricePaise?: number;
  maxPricePaise?: number;
  inStockOnly?: boolean;
  sortBy?: SortOption;
  page?: number;
  pageSize?: number;
  useNlp?: boolean;
}): Promise<ProductSearchResponse> {
  const query = new URLSearchParams();
  query.append('store_id', options.storeId);
  if (options.q && options.q.trim()) query.append('q', options.q.trim());
  if (options.category) query.append('category', options.category);
  if (options.brand) query.append('brand', options.brand);
  if (options.minPricePaise !== undefined) query.append('min_price_paise', String(options.minPricePaise));
  if (options.maxPricePaise !== undefined) query.append('max_price_paise', String(options.maxPricePaise));
  if (options.inStockOnly !== undefined) query.append('in_stock_only', String(options.inStockOnly));
  if (options.sortBy) query.append('sort_by', options.sortBy);
  if (options.page) query.append('page', String(options.page));
  if (options.pageSize) query.append('page_size', String(options.pageSize));
  if (options.useNlp !== undefined) query.append('use_nlp', String(options.useNlp));

  return request<ProductSearchResponse>(`/api/v1/search/products?${query.toString()}`);
}

/**
 * Autocomplete search suggestions (Edge n-gram OpenSearch).
 */
export async function fetchSearchSuggestions(
  storeId: string,
  query: string,
  limit: number = 8
): Promise<SearchSuggestionsResponse> {
  if (!query || query.trim().length < 2) {
    return { suggestions: [] };
  }
  const q = encodeURIComponent(query.trim());
  return request<SearchSuggestionsResponse>(
    `/api/v1/search/suggestions?store_id=${storeId}&q=${q}&limit=${limit}`
  );
}

/**
 * Store-specific filter facets (categories, brands, price range).
 */
export async function fetchStoreFilters(
  storeId: string,
  category?: string
): Promise<StoreFiltersResponse> {
  const qs = category ? `&category=${encodeURIComponent(category)}` : '';
  return request<StoreFiltersResponse>(`/api/v1/search/filters?store_id=${storeId}${qs}`);
}

/**
 * Real-time inventory balance lookup for store + product.
 */
export async function fetchProductStock(
  storeId: string,
  productId: string
): Promise<StockResponse> {
  return request<StockResponse>(`/api/v1/inventory/${storeId}/${productId}`);
}

/**
 * System health and root check endpoints.
 */
export async function fetchHealth(): Promise<SystemHealthResponse> {
  return request<SystemHealthResponse>('/api/health');
}

export async function fetchRoot(): Promise<RootResponse> {
  return request<RootResponse>('/api');
}

// ==========================================
// Authentication Endpoints
// ==========================================

/**
 * Authenticate customer or staff credentials and receive JWT token.
 */
export async function loginUser(payload: LoginPayload): Promise<TokenResponse> {
  const resp = await request<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  setAuthToken(resp.access_token);
  return resp;
}

/**
 * Public self-registration for new customers.
 */
export async function registerCustomer(payload: RegisterPayload): Promise<CustomerProfile> {
  return request<CustomerProfile>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Get current authenticated user profile.
 */
export async function fetchCurrentUser(): Promise<User> {
  return request<User>('/api/v1/auth/me');
}

/**
 * Get current authenticated customer profile (including delivery address).
 */
export async function fetchCustomerProfile(): Promise<CustomerProfile> {
  return request<CustomerProfile>('/api/v1/users/me/customer');
}

// ==========================================
// Cart & Stock Reservation Endpoints
// ==========================================

/**
 * Retrieve current customer's shopping cart with authoritative line items,
 * PostgreSQL pricing in paise, and earliest reservation expiration.
 */
export async function fetchCart(): Promise<CartResponse> {
  return request<CartResponse>('/api/v1/cart');
}

/**
 * Add product to cart and reserve stock for 10 minutes via PostgreSQL reserve_stock().
 */
export async function addCartItem(payload: CartItemAddPayload): Promise<CartResponse> {
  return request<CartResponse>('/api/v1/cart/items', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update cart item quantity with safe PostgreSQL reservation replacement.
 */
export async function updateCartItem(
  productId: string,
  payload: CartItemUpdatePayload
): Promise<CartResponse> {
  return request<CartResponse>(`/api/v1/cart/items/${productId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Remove product from cart and immediately release reserved stock via release_reservation().
 */
export async function removeCartItem(productId: string): Promise<CartResponse> {
  return request<CartResponse>(`/api/v1/cart/items/${productId}`, {
    method: 'DELETE',
  });
}

/**
 * Clear all items in active cart and release all stock reservations.
 */
export async function clearCart(): Promise<CartResponse> {
  return request<CartResponse>('/api/v1/cart', {
    method: 'DELETE',
  });
}

// ==========================================
// Checkout & Order Placement Endpoints
// ==========================================

/**
 * Submit checkout atomically with mandatory Idempotency-Key.
 */
export async function submitCheckout(
  payload: CheckoutPayload,
  idempotencyKey: string
): Promise<OrderResponse> {
  return request<OrderResponse>('/api/v1/checkout', {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
}

// ==========================================
// Store Manager API Endpoints
// ==========================================

/**
 * List products enriched with store-specific inventory status.
 */
export async function fetchManagerProducts(options?: {
  storeId?: string;
  category?: string;
  brand?: string;
  isActive?: boolean;
  skip?: number;
  limit?: number;
}): Promise<ManagerProduct[]> {
  const query = new URLSearchParams();
  if (options?.storeId) query.append('store_id', options.storeId);
  if (options?.category) query.append('category', options.category);
  if (options?.brand) query.append('brand', options.brand);
  if (options?.isActive !== undefined) query.append('is_active', String(options.isActive));
  if (options?.skip !== undefined) query.append('skip', String(options.skip));
  if (options?.limit !== undefined) query.append('limit', String(options.limit));

  const qs = query.toString();
  return request<ManagerProduct[]>(`/api/v1/manager/products${qs ? `?${qs}` : ''}`);
}

/**
 * Get product detail enriched with store inventory.
 */
export async function fetchManagerProductDetail(
  productId: string,
  storeId?: string
): Promise<ManagerProduct> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<ManagerProduct>(`/api/v1/manager/products/${productId}${qs}`);
}

/**
 * Create a new catalogue product with store inventory.
 */
export async function createManagerProduct(
  payload: ProductCreateManagerPayload,
  storeId?: string
): Promise<ManagerProduct> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<ManagerProduct>(`/api/v1/manager/products${qs}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Update product information.
 */
export async function updateManagerProduct(
  productId: string,
  payload: ProductUpdateManagerPayload,
  storeId?: string
): Promise<ManagerProduct> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<ManagerProduct>(`/api/v1/manager/products/${productId}${qs}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

/**
 * Safely deactivate a product (is_active = false).
 */
export async function deactivateManagerProduct(
  productId: string,
  storeId?: string
): Promise<ManagerProduct> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<ManagerProduct>(`/api/v1/manager/products/${productId}${qs}`, {
    method: 'DELETE',
  });
}

/**
 * Upload product image to Cloudinary.
 */
export async function uploadManagerProductImage(
  productId: string,
  file: File,
  storeId?: string
): Promise<ManagerProduct> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  const formData = new FormData();
  formData.append('file', file);

  return request<ManagerProduct>(`/api/v1/manager/products/${productId}/image${qs}`, {
    method: 'POST',
    body: formData,
  });
}

/**
 * Delete product image from Cloudinary and attributes.
 */
export async function deleteManagerProductImage(
  productId: string,
  storeId?: string
): Promise<ManagerProduct> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<ManagerProduct>(`/api/v1/manager/products/${productId}/image${qs}`, {
    method: 'DELETE',
  });
}

/**
 * List inventory for assigned store.
 */
export async function fetchStoreInventory(
  storeId?: string,
  skip?: number,
  limit?: number
): Promise<StockResponse[]> {
  const query = new URLSearchParams();
  if (storeId) query.append('store_id', storeId);
  if (skip !== undefined) query.append('skip', String(skip));
  if (limit !== undefined) query.append('limit', String(limit));

  const qs = query.toString();
  return request<StockResponse[]>(`/api/v1/manager/inventory${qs ? `?${qs}` : ''}`);
}

/**
 * List low-stock items for assigned store.
 */
export async function fetchLowStockInventory(storeId?: string): Promise<StockResponse[]> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<StockResponse[]>(`/api/v1/manager/inventory/low-stock${qs}`);
}

/**
 * Get inventory balance for single product.
 */
export async function fetchProductInventory(
  productId: string,
  storeId?: string
): Promise<StockResponse> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<StockResponse>(`/api/v1/manager/inventory/${productId}${qs}`);
}

/**
 * Perform audited stock adjustment (INCREASE, DECREASE, SET).
 */
export async function adjustProductStock(
  productId: string,
  payload: StockAdjustmentPayload,
  storeId?: string
): Promise<StockAdjustmentResponse> {
  const qs = storeId ? `?store_id=${storeId}` : '';
  return request<StockAdjustmentResponse>(`/api/v1/manager/inventory/${productId}/adjustments${qs}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Get inventory audit log history for a product.
 */
export async function fetchInventoryHistory(
  productId: string,
  storeId?: string,
  skip?: number,
  limit?: number
): Promise<InventoryAuditLog[]> {
  const query = new URLSearchParams();
  if (storeId) query.append('store_id', storeId);
  if (skip !== undefined) query.append('skip', String(skip));
  if (limit !== undefined) query.append('limit', String(limit));

  const qs = query.toString();
  return request<InventoryAuditLog[]>(`/api/v1/manager/inventory/${productId}/history${qs ? `?${qs}` : ''}`);
}

// ==========================================
// Administrator Endpoints
// ==========================================

/**
 * List all stores (active and inactive for administrators).
 */
export async function fetchStoresAdmin(options?: {
  state?: string;
  city?: string;
  isActive?: boolean;
  skip?: number;
  limit?: number;
}): Promise<Store[]> {
  const query = new URLSearchParams();
  if (options?.state) query.append('state', options.state);
  if (options?.city) query.append('city', options.city);
  if (options?.isActive !== undefined) query.append('is_active', String(options.isActive));
  if (options?.skip !== undefined) query.append('skip', String(options.skip));
  if (options?.limit !== undefined) query.append('limit', String(options.limit));

  const qs = query.toString();
  return request<Store[]>(`/api/v1/stores${qs ? `?${qs}` : ''}`);
}

/**
 * Get store details by ID.
 */
export async function fetchStoreById(storeId: string): Promise<Store> {
  return request<Store>(`/api/v1/stores/${storeId}`);
}

/**
 * List orders across stores with optional status filter.
 */
export async function fetchOrders(options?: {
  storeId?: string;
  status?: OrderStatus;
  skip?: number;
  limit?: number;
}): Promise<OrderResponse[]> {
  const query = new URLSearchParams();
  if (options?.storeId) query.append('store_id', options.storeId);
  if (options?.status) query.append('status', options.status);
  if (options?.skip !== undefined) query.append('skip', String(options.skip));
  if (options?.limit !== undefined) query.append('limit', String(options.limit));

  const qs = query.toString();
  return request<OrderResponse[]>(`/api/v1/orders${qs ? `?${qs}` : ''}`);
}

/**
 * Retrieve specific order details with status transition history.
 */
export async function fetchOrderDetail(orderId: string): Promise<OrderResponse> {
  return request<OrderResponse>(`/api/v1/orders/${orderId}`);
}

/**
 * Administrator cancellation of an order with inventory restoration.
 */
export async function cancelOrderAdmin(orderId: string, reason?: string): Promise<OrderResponse> {
  return request<OrderResponse>(`/api/v1/orders/${orderId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason || 'Administrator cancelled order and restored stock' }),
  });
}

/**
 * Lookup user profile by user ID.
 */
export async function fetchUserById(userId: string): Promise<User> {
  return request<User>(`/api/v1/users/${userId}`);
}

/**
 * Toggle user account status (active/inactive).
 */
export async function updateUserStatus(userId: string, isActive: boolean): Promise<User> {
  return request<User>(`/api/v1/users/${userId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive }),
  });
}

/**
 * Promote a user to STORE_MANAGER and assign to a store.
 */
export async function assignStoreManager(userId: string, storeId: string): Promise<User> {
  return request<User>(`/api/v1/users/${userId}/store-manager`, {
    method: 'PUT',
    body: JSON.stringify({ assigned_store_id: storeId }),
  });
}

/**
 * Retrieve system readiness and service health status.
 */
export async function fetchSystemHealth(): Promise<SystemHealthResponse> {
  return request<SystemHealthResponse>('/api/v1/health');
}

/**
 * Check live PostgreSQL connectivity and latency.
 */
export async function fetchDatabaseHealth(): Promise<DatabaseHealthResponse> {
  return request<DatabaseHealthResponse>('/api/v1/health/db');
}
