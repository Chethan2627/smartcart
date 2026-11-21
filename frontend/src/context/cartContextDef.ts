import { createContext, type MutableRefObject } from 'react';
import type { CartResponse, CartItemResponse } from '../types';

export interface ReservationTimerState {
  remainingSeconds: number;
  formattedTime: string;
  isWarning: boolean; // <= 180 seconds (3 mins)
  isUrgent: boolean;  // <= 60 seconds (1 min)
  isExpired: boolean;
}

export interface CartContextType {
  cart: CartResponse | null;
  items: CartItemResponse[];
  totalItems: number;
  totalPaise: number;
  isCartOpen: boolean;
  setIsCartOpen: (open: boolean) => void;
  isCheckoutOpen: boolean;
  setIsCheckoutOpen: (open: boolean) => void;
  isLoading: boolean;
  isMutating: boolean;
  reservationTimer: ReservationTimerState | null;
  addToCart: (storeId: string, productId: string, qty: number) => Promise<boolean>;
  updateQuantity: (productId: string, qty: number) => Promise<boolean>;
  removeItem: (productId: string) => Promise<boolean>;
  clearAllItems: () => Promise<boolean>;
  refreshCart: () => Promise<void>;
  expiryAlert: string | null;
  dismissExpiryAlert: () => void;
  cartError: string | null;
  clearCartError: () => void;
  onStockExpiredCallbacks: MutableRefObject<Set<() => void>>;
}

export const CartContext = createContext<CartContextType | undefined>(undefined);
