import React, { useState } from 'react';
import { X, Lock, Mail, User, Phone, MapPin, Sparkles, Loader2, AlertCircle } from 'lucide-react';
import { useAuth } from '../context/useAuth';

export const AuthModal: React.FC = () => {
  const { showAuthModal, setShowAuthModal, authModalMessage, login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');

  // Login form state
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Register form state
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regPhone, setRegPhone] = useState('');
  const [regAddress, setRegAddress] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!showAuthModal) return null;

  const handleClose = () => {
    setShowAuthModal(false);
    setError(null);
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginEmail.trim() || !loginPassword) {
      setError('Please provide both email and password');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await login({ email: loginEmail.trim(), password: loginPassword });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Invalid login credentials');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regName.trim() || !regEmail.trim() || !regPassword) {
      setError('Please fill in your name, email, and password');
      return;
    }
    if (regPassword.length < 8) {
      setError('Password must be at least 8 characters long');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await register({
        full_name: regName.trim(),
        email: regEmail.trim(),
        password: regPassword,
        phone: regPhone.trim() || undefined,
        address: regAddress.trim() || undefined,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  const fillDemoCustomer = async () => {
    setLoginEmail('demo@smartcart.in');
    setLoginPassword('Demo@123');
    setMode('login');
    setLoading(true);
    setError(null);
    try {
      await login({ email: 'demo@smartcart.in', password: 'Demo@123' });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to authenticate demo user');
    } finally {
      setLoading(false);
    }
  };

  const fillDemoManager = async () => {
    setLoginEmail('manager.bengaluru@smartcart.in');
    setLoginPassword('Demo@123');
    setMode('login');
    setLoading(true);
    setError(null);
    try {
      await login({ email: 'manager.bengaluru@smartcart.in', password: 'Demo@123' });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to authenticate store manager');
    } finally {
      setLoading(false);
    }
  };

  const fillDemoAdmin = async () => {
    setLoginEmail('admin@smartcart.in');
    setLoginPassword('Demo@123');
    setMode('login');
    setLoading(true);
    setError(null);
    try {
      await login({ email: 'admin@smartcart.in', password: 'Demo@123' });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to authenticate administrator');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div
        className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 bg-gradient-to-r from-emerald-600 to-teal-700 text-white relative">
          <button
            onClick={handleClose}
            className="absolute top-4 right-4 p-1.5 rounded-full bg-white/20 hover:bg-white/30 text-white transition-colors"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-white/20 text-xs font-medium text-emerald-100 mb-2">
            <Lock className="w-3.5 h-3.5" />
            <span>Secure SmartCart Portal</span>
          </div>
          <h2 className="text-xl font-bold tracking-tight">
            {mode === 'login' ? 'Welcome Back to SmartCart' : 'Create Your Customer Account'}
          </h2>
          <p className="text-xs text-emerald-100 mt-1">
            {authModalMessage || 'Log in to reserve fresh groceries with our 10-minute hold lock.'}
          </p>
        </div>

        {/* Mode Tabs */}
        <div className="flex border-b border-gray-200 bg-gray-50/50">
          <button
            type="button"
            onClick={() => { setMode('login'); setError(null); }}
            className={`flex-1 py-3 text-sm font-semibold border-b-2 transition-all ${
              mode === 'login'
                ? 'border-emerald-600 text-emerald-700 bg-white'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setMode('register'); setError(null); }}
            className={`flex-1 py-3 text-sm font-semibold border-b-2 transition-all ${
              mode === 'register'
                ? 'border-emerald-600 text-emerald-700 bg-white'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            New Customer
          </button>
        </div>

        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Quick Demo Buttons */}
          {mode === 'login' && (
            <div className="mb-5 space-y-2">
              <button
                type="button"
                onClick={fillDemoCustomer}
                disabled={loading}
                className="w-full py-2 px-3 rounded-xl border border-dashed border-emerald-300 bg-emerald-50/70 hover:bg-emerald-100/70 text-emerald-800 text-xs font-semibold flex items-center justify-center gap-2 transition-all hover:scale-[1.01]"
              >
                <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                <span>Instant Customer Login (demo@smartcart.in)</span>
              </button>
              <button
                type="button"
                onClick={fillDemoManager}
                disabled={loading}
                className="w-full py-2 px-3 rounded-xl border border-dashed border-indigo-300 bg-indigo-50/70 hover:bg-indigo-100/70 text-indigo-800 text-xs font-semibold flex items-center justify-center gap-2 transition-all hover:scale-[1.01]"
              >
                <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                <span>Instant Manager Login (manager.bengaluru@smartcart.in)</span>
              </button>
              <button
                type="button"
                onClick={fillDemoAdmin}
                disabled={loading}
                className="w-full py-2 px-3 rounded-xl border border-dashed border-purple-300 bg-purple-50/70 hover:bg-purple-100/70 text-purple-800 text-xs font-semibold flex items-center justify-center gap-2 transition-all hover:scale-[1.01]"
              >
                <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                <span>Instant Admin Login (admin@smartcart.in)</span>
              </button>
              <div className="relative my-4">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-white px-2 text-gray-400">or sign in with password</span>
                </div>
              </div>
            </div>
          )}

          {mode === 'login' ? (
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="email"
                    required
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="customer@example.com"
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="password"
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                <span>Sign In</span>
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegisterSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Full Name *
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    required
                    value={regName}
                    onChange={(e) => setRegName(e.target.value)}
                    placeholder="Priya Sharma"
                    className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Email Address *
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="email"
                    required
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    placeholder="priya@example.com"
                    className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Password (min 8 chars) *
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="password"
                    required
                    minLength={8}
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Phone Number
                </label>
                <div className="relative">
                  <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="tel"
                    value={regPhone}
                    onChange={(e) => setRegPhone(e.target.value)}
                    placeholder="+91-9876543210"
                    className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Delivery Address
                </label>
                <div className="relative">
                  <MapPin className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
                  <textarea
                    rows={2}
                    value={regAddress}
                    onChange={(e) => setRegAddress(e.target.value)}
                    placeholder="Flat 402, Green Glen Layout, Bellandur, Bengaluru"
                    className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-50"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                <span>Create Customer Account</span>
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
