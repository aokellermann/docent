import { requireAuth } from './lib/dal';
import DocentDashboard from './components/DocentDashboard';

/**
 * Server Component - Handles authentication
 * Following Next.js recommendations: auth check close to the data source
 */
export default async function HomePage() {
  // This automatically redirects to /login if not authenticated
  // Uses React cache() to avoid duplicate API calls during rendering
  await requireAuth();

  // User data is now available via UserProvider context
  // DocentDashboard will access it via useRequireAuth()
  return <DocentDashboard />;
}
