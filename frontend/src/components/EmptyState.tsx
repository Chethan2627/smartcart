import React from 'react';
import { SearchX, RotateCcw } from 'lucide-react';

interface EmptyStateProps {
  searchQuery?: string;
  hasFilters: boolean;
  onReset: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  searchQuery,
  hasFilters,
  onReset,
}) => {
  return (
    <div className="bg-white rounded-3xl border border-slate-200/90 p-8 sm:p-12 text-center max-w-xl mx-auto shadow-xs my-6">
      <div className="w-16 h-16 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4 border border-indigo-100">
        <SearchX className="w-8 h-8" />
      </div>

      <h3 className="text-lg sm:text-xl font-bold text-slate-900">
        No matching products found
      </h3>

      <p className="mt-2 text-xs sm:text-sm text-slate-500 max-w-md mx-auto">
        {searchQuery ? (
          <>
            We couldn't find any products matching &ldquo;
            <span className="font-semibold text-slate-800">{searchQuery}</span>
            &rdquo; at this store location.
          </>
        ) : (
          'There are no products matching your selected filter facets at this store.'
        )}
      </p>

      <div className="mt-6 flex items-center justify-center space-x-3">
        {hasFilters && (
          <button
            onClick={onReset}
            className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 active:scale-95 text-white font-bold text-xs sm:text-sm px-5 py-2.5 rounded-xl shadow-xs transition"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Reset All Filters</span>
          </button>
        )}
      </div>
    </div>
  );
};
