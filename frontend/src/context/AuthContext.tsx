import React, { useState, useEffect, useCallback } from 'react';
import type { User, CustomerProfile, LoginPayload, RegisterPayload } from '../types';
import {
  getAuthToken,
  clearAuthToken,
  loginUser,
  registerCustomer,
  fetchCurrentUser,
  fetchCustomerProfile,
  onAuthExpired,
} from '../api/client';
import { AuthContext } from './authContextDef';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [customerProfile, setCustomerProfile] = useState<CustomerProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [showAuthModal, setShowAuthModal] = useState<boolean>(false);
  const [authModalMessage, setAuthModalMessage] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setUser(null);
      setCustomerProfile(null);
      setIsLoading(false);
      return;
    }

    try {
      const u = await fetchCurrentUser();
      setUser(u);
      if (u.role === 'CUSTOMER') {
        try {
          const profile = await fetchCustomerProfile();
          setCustomerProfile(profile);
        } catch (e) {
          console.warn('Could not load customer profile:', e);
        }
      }
    } catch (err) {
      console.warn('Invalid or expired token on startup:', err);
      clearAuthToken();
      setUser(null);
      setCustomerProfile(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    const initAuth = async () => {
      if (!ignore) {
        await loadProfile();
      }
    };
    initAuth();

    const unsubscribe = onAuthExpired(() => {
      setUser(null);
      setCustomerProfile(null);
      setAuthModalMessage('Your session has expired. Please sign in again.');
      setShowAuthModal(true);
    });

    return () => {
      ignore = true;
      unsubscribe();
    };
  }, [loadProfile]);

  const promptAuth = (message?: string) => {
    setAuthModalMessage(message || 'Please sign in to proceed.');
    setShowAuthModal(true);
  };

  const login = async (payload: LoginPayload) => {
    await loginUser(payload);
    await loadProfile();
    setShowAuthModal(false);
    setAuthModalMessage(null);
  };

  const register = async (payload: RegisterPayload) => {
    await registerCustomer(payload);
    // After registration, log the user in immediately
    await loginUser({ email: payload.email, password: payload.password });
    await loadProfile();
    setShowAuthModal(false);
    setAuthModalMessage(null);
  };

  const logout = () => {
    clearAuthToken();
    setUser(null);
    setCustomerProfile(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        customerProfile,
        isAuthenticated: !!user,
        isLoading,
        showAuthModal,
        setShowAuthModal,
        authModalMessage,
        promptAuth,
        login,
        register,
        logout,
        refreshUser: loadProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
