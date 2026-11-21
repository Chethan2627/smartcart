import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import type { CartResponse } from '../types';
import {
  fetchCart,
  addCartItem,
  updateCartItem,
  removeCartItem,
  clearCart as apiClearCart,
} from '../api/client';
import { useAuth } from './useAuth';
import { CartContext, type ReservationTimerState } from './cartContextDef';

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, user, promptAuth } = useAuth();
  const [cart, setCart] = useState<CartResponse | null>(null);
  const [isCartOpen, setIsCartOpen] = useState<boolean>(false);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isMutating, setIsMutating] = useState<boolean>(false);
  const [cartError, setCartError] = useState<string | null>(null);
  const [expiryAlert, setExpiryAlert] = useState<string | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);

  const onStockExpiredCallbacks = useRef<Set<() => void>>(new Set());

  // 1. Fetch backend cart when authenticated as CUSTOMER
  const loadCart = useCallback(async () => {
    if (!isAuthenticated || (user && user.role !== 'CUSTOMER')) {
      setCart(null);
      return;
    }
    setIsLoading(true);
    try {
      const serverCart = await fetchCart();
      setCart(serverCart);
    } catch (err: unknown) {
      console.warn('Failed to fetch cart from server:', err);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, user]);

  useEffect(() => {
    let ignore = false;
    const run = async () => {
      if (!ignore) {
        await loadCart();
      }
    };
    run();
    return () => {
      ignore = true;
    };
  }, [loadCart]);

  // 2. Real-time countdown timer synchronized with backend earliest_expiration
  useEffect(() => {
    if (!cart?.earliest_expiration || cart.items.length === 0) {
      return;
    }

    const computeRemaining = () => {
      const expTime = new Date(cart.earliest_expiration!).getTime();
      return Math.max(0, Math.floor((expTime - Date.now()) / 1000));
    };

    const timer = setTimeout(() => {
      setRemainingSeconds(computeRemaining());
    }, 0);

    const interval = setInterval(() => {
      const remaining = computeRemaining();
      setRemainingSeconds(remaining);
      if (remaining === 0) {
        clearInterval(interval);
      }
    }, 1000);

    return () => {
      clearTimeout(timer);
      clearInterval(interval);
    };
  }, [cart?.earliest_expiration, cart?.items.length]);

  // 3. Compute timer state based on authoritative backend timestamp
  const reservationTimer: ReservationTimerState | null = useMemo(() => {
    if (!cart?.earliest_expiration || cart.items.length === 0 || remainingSeconds === null) {
      return null;
    }
    const mins = Math.floor(remainingSeconds / 60);
    const secs = remainingSeconds % 60;
    return {
      remainingSeconds,
      formattedTime: `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`,
      isWarning: remainingSeconds <= 180 && remainingSeconds > 60,
      isUrgent: remainingSeconds <= 60 && remainingSeconds > 0,
      isExpired: remainingSeconds === 0,
    };
  }, [remainingSeconds, cart?.earliest_expiration, cart?.items.length]);

  // 4. Handle reservation expiry trigger
  const hasExpiredRef = useRef(false);
  useEffect(() => {
    if (remainingSeconds === 0 && !hasExpiredRef.current && (cart?.items.length || 0) > 0) {
      hasExpiredRef.current = true;
      // Refresh cart from backend to confirm expired reservations release
      fetchCart()
        .then((updated) => {
          setCart(updated);
          setExpiryAlert('Your 10-minute stock reservation expired. Reserved items have been released back to store inventory.');
          onStockExpiredCallbacks.current.forEach((cb) => {
            try {
              cb();
            } catch (e) {
              console.error(e);
            }
          });
        })
        .catch(console.error);
    } else if (remainingSeconds !== null && remainingSeconds > 0) {
      hasExpiredRef.current = false;
    }
  }, [remainingSeconds, cart?.items.length, onStockExpiredCallbacks]);

  // 5. Add to Cart with 10-Minute Hold Reservation
  const addToCart = async (storeId: string, productId: string, qty: number): Promise<boolean> => {
    if (!isAuthenticated) {
      promptAuth('Sign in to reserve items in your shopping cart with our 10-minute hold guarantee.');
      return false;
    }

    if (user && user.role !== 'CUSTOMER') {
      setCartError('Staff and Admin accounts cannot place retail customer orders. Please sign in with a Customer account to shop.');
      return false;
    }

    setIsMutating(true);
    setCartError(null);
    try {
      const updatedCart = await addCartItem({
        store_id: storeId,
        product_id: productId,
        qty,
      });
      setCart(updatedCart);
      setIsCartOpen(true);
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to add product to cart';
      setCartError(msg);
      return false;
    } finally {
      setIsMutating(false);
    }
  };

  // 6. Update Quantity
  const updateQuantity = async (productId: string, qty: number): Promise<boolean> => {
    if (!isAuthenticated) return false;

    if (qty <= 0) {
      return removeItem(productId);
    }

    setIsMutating(true);
    setCartError(null);
    try {
      const updatedCart = await updateCartItem(productId, { qty });
      setCart(updatedCart);
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update item quantity';
      setCartError(msg);
      return false;
    } finally {
      setIsMutating(false);
    }
  };

  // 7. Remove item
  const removeItem = async (productId: string): Promise<boolean> => {
    if (!isAuthenticated) return false;

    setIsMutating(true);
    setCartError(null);
    try {
      const updatedCart = await removeCartItem(productId);
      setCart(updatedCart);
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to remove item';
      setCartError(msg);
      return false;
    } finally {
      setIsMutating(false);
    }
  };

  // 8. Clear Cart
  const clearAllItems = async (): Promise<boolean> => {
    if (!isAuthenticated) return false;

    setIsMutating(true);
    setCartError(null);
    try {
      const updatedCart = await apiClearCart();
      setCart(updatedCart);
      return true;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to clear cart';
      setCartError(msg);
      return false;
    } finally {
      setIsMutating(false);
    }
  };

  const dismissExpiryAlert = () => setExpiryAlert(null);
  const clearCartError = () => setCartError(null);

  return (
    <CartContext.Provider
      value={{
        cart,
        items: cart?.items || [],
        totalItems: cart?.total_items || 0,
        totalPaise: cart?.total_paise || 0,
        isCartOpen,
        setIsCartOpen,
        isCheckoutOpen,
        setIsCheckoutOpen,
        isLoading,
        isMutating,
        reservationTimer,
        addToCart,
        updateQuantity,
        removeItem,
        clearAllItems,
        refreshCart: loadCart,
        expiryAlert,
        dismissExpiryAlert,
        cartError,
        clearCartError,
        onStockExpiredCallbacks,
      }}
    >
      {children}
    </CartContext.Provider>
  );
};
