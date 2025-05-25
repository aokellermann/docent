import DocentDashboard from '../components/DocentDashboard';

/**
 * Main Dashboard Page - Server Component
 *
 * Authentication is handled by the dashboard layout, so this page
 * is guaranteed to only render for authenticated users.
 */
export default async function DashboardPage() {
  return <DocentDashboard />;
}
