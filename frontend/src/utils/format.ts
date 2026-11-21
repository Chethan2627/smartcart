/**
 * SmartCart 2.0 - Formatting and Image Helpers
 */

/**
 * Format Indian paise into INR currency display.
 * 149900 paise -> ₹1,499
 */
export function formatPrice(paise: number): string {
  const rupees = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: rupees % 1 === 0 ? 0 : 2,
  }).format(rupees);
}

/**
 * Calculate synthetic original MRP (15-25% higher) for savings presentation.
 */
export function getOriginalPrice(paise: number): string {
  const markupMultiplier = 1.2;
  const originalRupees = Math.round((paise * markupMultiplier) / 100);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(originalRupees);
}

/**
 * Deterministic curated high-resolution photography for catalogue items.
 */
const CURATED_IMAGE_MAP: Record<string, string> = {
  'BT-HEAD-001':
    'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80',
  'PHONE-001':
    'https://images.unsplash.com/photo-1592899677977-9c10ca588bbd?w=800&auto=format&fit=crop&q=80',
  'RICE-5KG':
    'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=800&auto=format&fit=crop&q=80',
  'MILK-1L':
    'https://images.unsplash.com/photo-1550583724-b2692b85b150?w=800&auto=format&fit=crop&q=80',
  'ATTA-10KG':
    'https://images.unsplash.com/photo-1509440159596-0249088772ff?w=800&auto=format&fit=crop&q=80',
};

const CATEGORY_FALLBACK_MAP: Record<string, string> = {
  electronics:
    'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80',
  mobiles:
    'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=800&auto=format&fit=crop&q=80',
  grocery:
    'https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&auto=format&fit=crop&q=80',
  'gourmet & spices':
    'https://images.unsplash.com/photo-1596040033229-a9821ebd058d?w=800&auto=format&fit=crop&q=80',
};

export function getProductImage(
  sku?: string,
  category?: string | null,
  customImageUrl?: string | null
): string {
  if (customImageUrl && customImageUrl.startsWith('http')) {
    return customImageUrl;
  }
  if (sku && CURATED_IMAGE_MAP[sku]) {
    return CURATED_IMAGE_MAP[sku];
  }
  const normalizedCat = (category || '').trim().toLowerCase();
  if (CATEGORY_FALLBACK_MAP[normalizedCat]) {
    return CATEGORY_FALLBACK_MAP[normalizedCat];
  }
  return 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&auto=format&fit=crop&q=80';
}

/**
 * Deterministic review score and count for presentation.
 */
export function getProductRating(sku?: string): { rating: number; reviews: number } {
  if (!sku) return { rating: 4.7, reviews: 142 };
  let hash = 0;
  for (let i = 0; i < sku.length; i++) {
    hash = sku.charCodeAt(i) + ((hash << 5) - hash);
  }
  const rating = 4.3 + (Math.abs(hash) % 7) / 10;
  const reviews = 45 + (Math.abs(hash) % 350);
  return {
    rating: Number(rating.toFixed(1)),
    reviews,
  };
}
