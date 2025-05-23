'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { Loader2 } from 'lucide-react';

import { useUser } from '../../contexts/UserContext';
import LoginPage from '../../login/page';

interface AuthWrapperProps {
  children: React.ReactNode;
}

const publicRoutes = ['/login', '/signup'];

export const AuthWrapper = ({ children }: AuthWrapperProps) => {
  const { user, loading } = useUser();
  const pathname = usePathname();
  const router = useRouter();

  // Redirect authenticated users away from public routes
  useEffect(() => {
    if (!loading && user && publicRoutes.includes(pathname)) {
      router.replace('/');
    }
  }, [user, loading, pathname, router]);

  // If authenticated user is on public route, show loading while redirecting
  if (loading || (user && publicRoutes.includes(pathname))) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  // If current route is public and user is not authenticated, render children
  if (publicRoutes.includes(pathname)) {
    return <>{children}</>;
  }

  // For protected routes, check authentication
  if (!user) {
    // User is not authenticated, show login page
    return <LoginPage />;
  }

  // User is authenticated, render the protected content
  return <>{children}</>;
};
