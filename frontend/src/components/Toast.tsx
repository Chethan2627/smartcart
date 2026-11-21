import React, { useEffect } from 'react';
import { CheckCircle2, X } from 'lucide-react';

interface ToastProps {
  message: string;
  onClose: () => void;
  duration?: number;
}

export const Toast: React.FC<ToastProps> = ({ message, onClose, duration = 3000 }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center space-x-3 bg-slate-900 text-white px-4 py-3 rounded-xl shadow-2xl border border-slate-700 animate-slide-up">
      <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
        <CheckCircle2 className="w-5 h-5" />
      </div>
      <p className="text-sm font-medium pr-2">{message}</p>
      <button
        onClick={onClose}
        className="text-slate-400 hover:text-white transition p-1 rounded-lg hover:bg-slate-800"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
