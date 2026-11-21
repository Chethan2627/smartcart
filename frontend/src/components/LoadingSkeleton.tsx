import React from 'react';

export const LoadingSkeleton: React.FC = () => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-6">
      {Array.from({ length: 8 }).map((_, idx) => (
        <div
          key={idx}
          className="bg-white rounded-2xl border border-slate-200/80 p-4 flex flex-col space-y-4 animate-pulse"
        >
          {/* Image skeleton */}
          <div className="aspect-square w-full bg-slate-200 rounded-xl" />
          {/* Category tag */}
          <div className="h-3 bg-slate-200 rounded-md w-1/3" />
          {/* Title */}
          <div className="space-y-1.5">
            <div className="h-4 bg-slate-200 rounded-md w-full" />
            <div className="h-4 bg-slate-200 rounded-md w-4/5" />
          </div>
          {/* Price & button */}
          <div className="flex items-center justify-between pt-3 border-t border-slate-100">
            <div className="h-5 bg-slate-200 rounded-md w-24" />
            <div className="h-8 bg-slate-200 rounded-xl w-16" />
          </div>
        </div>
      ))}
    </div>
  );
};
