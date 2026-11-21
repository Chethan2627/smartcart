/**
 * SmartCart 2.0 - Core Frontend TypeScript Type Definitions
 * Directly aligned with FastAPI backend Pydantic schemas.
 */

export interface Store {
  id: string;
  code: string;
  name: string;
  city: string;
  state: string;
  address?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ProductAttributes {
  color?: string;
  storage?: string;
  connectivity?: string;
  weight?: string;
  volume?: string;
  grade?: string;
  origin?: string;
  image?: {
    url?: string;
    secure_url?: string;
    public_id?: string;
  };
  image_url?: string;
  [key: string]: unknown;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  description?: string | null;
  brand?: string | null;
  category?: string | null;
  price_paise: number;
  attributes: ProductAttributes;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductSearchResultItem {
  id: string;
  product_id: string;
  store_id: string;
  sku: string;
  name: string;
  brand?: string | null;
  category?: string | null;
  description?: string | null;
  price_paise: number;
  image_url?: string | null;
  is_active: boolean;
  qty_on_hand: number;
  qty_reserved: number;
  qty_available: number;
  is_in_stock: boolean;
  score?: number;
}

export interface FacetBucket {
  name: string;
  count: number;
}

export interface SearchFilterFacets {
  categories: FacetBucket[];
  brands: FacetBucket[];
  min_price_paise: number;
  max_price_paise: number;
}

export interface ProductSearchResponse {
  items: ProductSearchResultItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  filters: SearchFilterFacets;
  applied_nlp_filters?: Record<string, unknown>;
}

export interface SearchSuggestionItem {
  text: string;
  product_id: string;
  sku: string;
  category?: string | null;
  brand?: string | null;
  price_paise?: number | null;
  qty_available?: number | null;
  is_in_stock?: boolean | null;
}

export interface SearchSuggestionsResponse {
  suggestions: SearchSuggestionItem[];
}

export interface StoreFiltersResponse {
  store_id: string;
  categories: FacetBucket[];
  brands: FacetBucket[];
  min_price_paise: number;
  max_price_paise: number;
}

export interface StockResponse {
  store_id: string;
  product_id: string;
  qty_on_hand: number;
  qty_reserved: number;
  qty_available: number;
  is_low_stock: boolean;
  is_in_stock: boolean;
  low_stock_threshold: number;
}

export interface CartItem {
  productId: string;
  storeId: string;
  sku: string;
  name: string;
  pricePaise: number;
  quantity: number;
  imageUrl?: string;
  maxAvailable: number;
}

export type SortOption =
  | 'relevance'
  | 'price_asc'
  | 'price_desc'
  | 'name_asc'
  | 'newest';

// ==========================================
// Authentication Types
// ==========================================

export type UserRole = 'CUSTOMER' | 'STORE_MANAGER' | 'ADMIN' | 'SUPER_ADMIN';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  assigned_store_id?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomerProfile {
  id: string;
  user_id: string;
  phone?: string | null;
  address?: string | null;
  created_at: string;
  user?: User;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  phone?: string;
  address?: string;
}

// ==========================================
// Backend Cart & Reservation Types
// ==========================================

export interface CartItemResponse {
  reservation_id: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  unit_price_paise: number;
  qty: number;
  item_subtotal_paise: number;
  expires_at: string;
}

export interface CartResponse {
  store_id?: string | null;
  items: CartItemResponse[];
  total_items: number;
  total_paise: number;
  earliest_expiration?: string | null;
}

export interface CartItemAddPayload {
  store_id: string;
  product_id: string;
  qty: number;
}

export interface CartItemUpdatePayload {
  qty: number;
}

// ==========================================
// Checkout & Order Types
// ==========================================

export type OrderStatus =
  | 'PENDING'
  | 'CONFIRMED'
  | 'PACKED'
  | 'SHIPPED'
  | 'DELIVERED'
  | 'CANCELLED';

export interface OrderItem {
  id: number;
  order_id: string;
  product_id: string;
  qty: number;
  unit_price_paise: number;
  item_subtotal_paise?: number;
}

export interface OrderStatusHistory {
  id: number;
  order_id: string;
  from_status?: OrderStatus | null;
  to_status: OrderStatus;
  changed_at: string;
}

export interface OrderResponse {
  id: string;
  order_number: string;
  customer_id: string;
  store_id: string;
  status: OrderStatus;
  total_paise: number;
  items: OrderItem[];
  status_history: OrderStatusHistory[];
  created_at: string;
  updated_at: string;
}

export interface CheckoutPayload {
  store_id: string;
  delivery_address?: string;
}

// ==========================================
// Store Manager Types
// ==========================================

export type StockAdjustmentType = 'INCREASE' | 'DECREASE' | 'SET';

export interface ProductImage {
  url: string;
  secure_url?: string | null;
  public_id?: string | null;
  format?: string | null;
  width?: number | null;
  height?: number | null;
  bytes?: number | null;
}

export interface ManagerProduct {
  id: string;
  sku: string;
  name: string;
  description?: string | null;
  brand?: string | null;
  category?: string | null;
  price_paise: number;
  attributes: Record<string, unknown>;
  image?: ProductImage | null;
  is_active: boolean;
  store_id?: string | null;
  qty_on_hand?: number | null;
  qty_reserved?: number | null;
  qty_available?: number | null;
  low_stock_threshold?: number | null;
  is_low_stock?: boolean | null;
  created_at: string;
  updated_at: string;
}

export interface ProductCreateManagerPayload {
  sku: string;
  name: string;
  description?: string;
  brand?: string;
  category?: string;
  price_paise: number;
  attributes?: Record<string, unknown>;
  initial_stock?: number;
  low_stock_threshold?: number;
}

export interface ProductUpdateManagerPayload {
  name?: string;
  description?: string;
  brand?: string;
  category?: string;
  attributes?: Record<string, unknown>;
  price_paise?: number;
  is_active?: boolean;
}

export interface StockAdjustmentPayload {
  adjustment_type: StockAdjustmentType;
  quantity: number;
  reason: string;
  low_stock_threshold?: number;
}

export interface StockAdjustmentResponse {
  store_id: string;
  product_id: string;
  old_on_hand: number;
  new_on_hand: number;
  qty_reserved: number;
  qty_available: number;
  adjustment_type: StockAdjustmentType;
  quantity_delta: number;
  reason: string;
  low_stock_threshold: number;
  is_low_stock: boolean;
  updated_at: string;
}

export interface InventoryAuditLog {
  id: number;
  store_id: string;
  product_id: string;
  old_on_hand: number;
  new_on_hand: number;
  old_reserved: number;
  new_reserved: number;
  reason: string;
  changed_at: string;
}

// ==========================================
// Admin & System Health Types
// ==========================================

export interface SystemHealthServices {
  postgresql_configured: boolean;
  kafka_configured: boolean;
  opensearch_configured: boolean;
}

export interface SystemHealthResponse {
  status: string;
  environment: string;
  version: string;
  services: SystemHealthServices;
  timestamp: string;
}

export interface DatabaseHealthResponse {
  status: string;
  database: string;
  database_connected: boolean;
  latency_ms?: number;
  error?: string;
  timestamp: string;
}

export interface StoreManagerAssignPayload {
  assigned_store_id: string;
}

export interface UserStatusUpdatePayload {
  is_active: boolean;
}


