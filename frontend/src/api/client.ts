export interface SystemHealthResponse {
  status: string;
  environment: string;
  version: string;
  services: {
    postgresql_configured: boolean;
    kafka_configured: boolean;
    opensearch_configured: boolean;
  };
  timestamp: string;
}

export interface RootResponse {
  project: string;
  tagline: string;
  team: string;
  institution: string;
  status: string;
  docs_url: string;
  timestamp: string;
}

/**
 * API Base URL Configuration:
 * - In local development: defaults to '' (empty string), enabling Vite's reverse proxy
 *   to handle '/api' requests without CORS issues.
 * - In production: connects to the deployed Render backend URL via import.meta.env.VITE_API_URL.
 */
const rawBaseUrl = import.meta.env.VITE_API_URL || '';
export const API_BASE_URL = rawBaseUrl.replace(/\/+$/, '');

export function getApiBaseUrl(): string {
  return API_BASE_URL || '(Vite /api proxy)';
}

export async function fetchHealth(): Promise<SystemHealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`, {
    headers: {
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok) {
    throw new Error(`Health check failed with status: ${response.status}`);
  }
  return response.json();
}

export async function fetchRoot(): Promise<RootResponse> {
  const response = await fetch(`${API_BASE_URL}/api`, {
    headers: {
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok) {
    throw new Error(`Root request failed with status: ${response.status}`);
  }
  return response.json();
}
