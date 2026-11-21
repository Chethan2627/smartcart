import React from 'react';
import {
  Zap,
  ShieldCheck,
  Search,
  Clock,
  Sparkles,
  Headphones,
  Smartphone,
  ShoppingBasket,
} from 'lucide-react';

interface HeroBannerProps {
  activeCategory: string | null;
  onSelectCategory: (category: string | null) => void;
  storeName?: string;
  storeCity?: string;
}

export const HeroBanner: React.FC<HeroBannerProps> = ({
  activeCategory,
  onSelectCategory,
  storeName = 'SmartCart Bengaluru',
  storeCity = 'Bengaluru',
}) => {
  const categories = [
    { id: null, label: 'All Products', icon: Sparkles },
    { id: 'Electronics', label: 'Electronics', icon: Headphones },
    { id: 'Mobiles', label: 'Mobiles & 5G', icon: Smartphone },
    { id: 'Grocery', label: 'Daily Grocery', icon: ShoppingBasket },
  ];

  return (
    <section className="relative overflow-hidden bg-gradient-to-b from-indigo-950 via-slate-900 to-slate-950 text-white pt-8 pb-12 sm:pt-12 sm:pb-16 px-4 sm:px-6 lg:px-8 border-b border-slate-800">
      {/* Background ambient lighting effects */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-violet-500/10 rounded-full blur-3xl pointer-events-none" />

      <div className="max-w-7xl mx-auto relative z-10">
        <div className="text-center max-w-3xl mx-auto">
          {/* Active Store Badge */}
          <div className="inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-full bg-indigo-500/15 border border-indigo-400/30 text-indigo-300 text-xs font-semibold mb-5 shadow-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span>Fulfillment Hub: {storeName} ({storeCity})</span>
          </div>

          {/* Main Headline */}
          <h1 className="text-3xl sm:text-5xl font-black tracking-tight leading-tight sm:leading-none text-white">
            Smart Shopping.{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-sky-300 to-pink-400">
              Guaranteed Stock.
            </span>
          </h1>

          <p className="mt-4 text-sm sm:text-base text-slate-300 font-normal leading-relaxed">
            Multi-store retail platform engineered with Aiven PostgreSQL, Kafka event-driven transactional outbox, and OpenSearch typo-tolerance. Enjoy guaranteed 10-minute checkout reservations with zero overselling.
          </p>
        </div>

        {/* 4 Value Proposition Highlights */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mt-8 max-w-5xl mx-auto">
          <div className="bg-slate-800/60 backdrop-blur-xs border border-slate-700/60 p-3.5 rounded-2xl flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-white">10-Min Cart Hold</p>
              <p className="text-[11px] text-slate-400">Stock reserved on add-to-cart</p>
            </div>
          </div>

          <div className="bg-slate-800/60 backdrop-blur-xs border border-slate-700/60 p-3.5 rounded-2xl flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-white">Zero Overselling</p>
              <p className="text-[11px] text-slate-400">PostgreSQL row-locked balances</p>
            </div>
          </div>

          <div className="bg-slate-800/60 backdrop-blur-xs border border-slate-700/60 p-3.5 rounded-2xl flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0">
              <Search className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-white">Typo-Tolerant</p>
              <p className="text-[11px] text-slate-400">OpenSearch NLP query expansion</p>
            </div>
          </div>

          <div className="bg-slate-800/60 backdrop-blur-xs border border-slate-700/60 p-3.5 rounded-2xl flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-pink-500/20 text-pink-400 flex items-center justify-center shrink-0">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-white">15-Min Delivery</p>
              <p className="text-[11px] text-slate-400">Direct from local dark-store</p>
            </div>
          </div>
        </div>

        {/* Category Quick Filters */}
        <div className="mt-8 flex items-center justify-center flex-wrap gap-2 sm:gap-3">
          {categories.map((cat) => {
            const Icon = cat.icon;
            const isSelected = activeCategory === cat.id;
            return (
              <button
                key={String(cat.id)}
                onClick={() => onSelectCategory(cat.id)}
                className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold transition shadow-sm ${
                  isSelected
                    ? 'bg-indigo-600 text-white ring-2 ring-indigo-400 shadow-indigo-600/30'
                    : 'bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-white border border-slate-700'
                }`}
              >
                <Icon className={`w-4 h-4 ${isSelected ? 'text-white' : 'text-indigo-400'}`} />
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
};
