import React from 'react';
import {
  ShieldCheck,
  Server,
  Zap,
  ExternalLink,
  Heart,
} from 'lucide-react';

const CURRENT_YEAR = new Date().getFullYear();

export const Footer: React.FC = () => {
  return (
    <footer className="bg-slate-900 text-slate-400 text-xs border-t border-slate-800 mt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-12">
          {/* Col 1: SmartCart Info */}
          <div className="space-y-3 md:col-span-1">
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-extrabold text-sm">
                S
              </div>
              <span className="font-extrabold text-lg text-white">
                Smart<span className="text-indigo-400">Cart</span>
              </span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                v2.0
              </span>
            </div>
            <p className="text-slate-400 leading-relaxed text-xs">
              Next-generation retail platform with real-time multi-store inventory hold, zero overselling guarantees, and AI search.
            </p>
          </div>

          {/* Col 2: Architecture Highlights */}
          <div className="space-y-2">
            <h4 className="font-bold text-white text-xs uppercase tracking-wider mb-3">
              Cloud Infrastructure
            </h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                <span>Aiven PostgreSQL 18.7</span>
              </div>
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="w-2 h-2 rounded-full bg-sky-400" />
                <span>Aiven Apache Kafka 4.3</span>
              </div>
              <div className="flex items-center space-x-2 text-slate-300">
                <span className="w-2 h-2 rounded-full bg-indigo-400" />
                <span>Aiven OpenSearch 3.6</span>
              </div>
            </div>
          </div>

          {/* Col 3: Customer Guarantees */}
          <div className="space-y-2">
            <h4 className="font-bold text-white text-xs uppercase tracking-wider mb-3">
              Customer Guarantees
            </h4>
            <ul className="space-y-2 text-xs text-slate-300">
              <li className="flex items-center space-x-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>10-Minute Cart Hold</span>
              </li>
              <li className="flex items-center space-x-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>15-Minute Local Delivery</span>
              </li>
              <li className="flex items-center space-x-1.5">
                <Server className="w-3.5 h-3.5 text-indigo-400" />
                <span>Transactional Outbox Events</span>
              </li>
            </ul>
          </div>

          {/* Col 4: Project Info */}
          <div className="space-y-3">
            <h4 className="font-bold text-white text-xs uppercase tracking-wider mb-3">
              Developer & API
            </h4>
            <div className="space-y-2 text-xs">
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noreferrer"
                className="flex items-center space-x-1.5 text-indigo-400 hover:text-indigo-300 transition"
              >
                <span>Interactive Swagger API Docs</span>
                <ExternalLink className="w-3 h-3" />
              </a>
              <p className="text-slate-400">Team Hack Hive • CIT Gubbi</p>
            </div>
          </div>
        </div>

        {/* Bottom copyright row */}
        <div className="pt-8 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between text-slate-500 text-[11px] gap-4">
          <p>© {CURRENT_YEAR} SmartCart 2.0. All rights reserved.</p>
          <p className="flex items-center space-x-1">
            <span>Built with</span>
            <Heart className="w-3 h-3 text-rose-500 fill-rose-500" />
            <span>for intelligent, reliable retail experiences</span>
          </p>
        </div>
      </div>
    </footer>
  );
};
