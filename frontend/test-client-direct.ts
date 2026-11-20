/**
 * Direct Unit & Integration Test for frontend/src/api/client.ts
 *
 * This test imports and executes the actual exported functions:
 *   - fetchHealth()
 *   - fetchRoot()
 *   - getApiBaseUrl()
 *   - API_BASE_URL
 * directly from './src/api/client' using vite-node.
 */

// In browser environments, relative fetch('/api/...') is resolved against window.location.origin.
// In Node.js environment, we emulate this browser origin resolution for relative URLs:
const originalFetch = globalThis.fetch;
const BROWSER_ORIGIN = 'http://127.0.0.1:5173';

globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  if (typeof input === 'string' && input.startsWith('/')) {
    input = `${BROWSER_ORIGIN}${input}`;
  }
  return originalFetch(input, init);
};

// Now import the ACTUAL client module functions and constants
import { fetchHealth, fetchRoot, getApiBaseUrl, API_BASE_URL } from './src/api/client';

async function runDirectClientTests() {
  console.log('==================================================================');
  console.log('SMARTCART 2.0 – DIRECT CLIENT FUNCTION IMPORT & EXECUTION TEST');
  console.log('==================================================================\n');

  console.log('[Test 1] Inspect Imported Module Constants & Helpers:');
  console.log(`- API_BASE_URL value: "${API_BASE_URL}"`);
  console.log(`- getApiBaseUrl() output: "${getApiBaseUrl()}"`);
  if (API_BASE_URL === '' && getApiBaseUrl() === '(Vite /api proxy)') {
    console.log('>>> Test 1 Passed: Module correctly configured for Vite proxy.\n');
  } else {
    console.error('>>> Test 1 Failed: Unexpected default configuration.\n');
    process.exit(1);
  }

  console.log('[Test 2] Execute Actual fetchHealth() Function:');
  try {
    const health = await fetchHealth();
    console.log('Returned Health Data:');
    console.log(`  - status: ${health.status}`);
    console.log(`  - environment: ${health.environment}`);
    console.log(`  - version: ${health.version}`);
    console.log(`  - services: PG=${health.services.postgresql_configured}, Kafka=${health.services.kafka_configured}, OS=${health.services.opensearch_configured}`);
    if (health.status === 'healthy' && health.environment === 'development') {
      console.log('>>> Test 2 Passed: Actual fetchHealth() function succeeded via proxy.\n');
    } else {
      console.error('>>> Test 2 Failed: Unexpected response data.\n');
      process.exit(1);
    }
  } catch (err: any) {
    console.error(`>>> Test 2 Failed with error: ${err.message}\n`);
    process.exit(1);
  }

  console.log('[Test 3] Execute Actual fetchRoot() Function:');
  try {
    const root = await fetchRoot();
    console.log('Returned Root Data:');
    console.log(`  - project: ${root.project}`);
    console.log(`  - team: ${root.team}`);
    console.log(`  - institution: ${root.institution}`);
    console.log(`  - status: ${root.status}`);
    if (root.project === 'SmartCart 2.0' && root.team === 'Hack Hive') {
      console.log('>>> Test 3 Passed: Actual fetchRoot() function succeeded via proxy.\n');
    } else {
      console.error('>>> Test 3 Failed: Unexpected response data.\n');
      process.exit(1);
    }
  } catch (err: any) {
    console.error(`>>> Test 3 Failed with error: ${err.message}\n`);
    process.exit(1);
  }

  console.log('==================================================================');
  console.log('ALL DIRECT API CLIENT FUNCTION TESTS PASSED SUCCESSFULLY');
  console.log('==================================================================');
}

runDirectClientTests();
