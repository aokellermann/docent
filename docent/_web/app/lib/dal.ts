import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { cache } from 'react';

export interface User {
  user_id: string;
  email: string;
}

export interface Session {
  user: User;
  sessionId: string;
}

/**
 * Gets the API host for server-side calls
 * Uses INTERNAL_API_HOST when available, falls back to NEXT_PUBLIC_API_HOST
 */
function getServerApiHost(): string {
  // Prefer INTERNAL_API_HOST for server-side calls (container-to-container)
  const internalApiHost = process.env.INTERNAL_API_HOST;
  const publicApiHost = process.env.NEXT_PUBLIC_API_HOST;

  const apiHost = internalApiHost || publicApiHost;

  if (!apiHost) {
    throw new Error(
      'Neither INTERNAL_API_HOST nor NEXT_PUBLIC_API_HOST is set'
    );
  }

  return apiHost;
}

/**
 * Verifies the session with the backend
 * This is the core auth check function
 */
export const verifySession = cache(async (): Promise<Session | null> => {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get('docent_session_id');

  if (!sessionCookie?.value) {
    return null;
  }

  try {
    const apiHost = getServerApiHost();
    const response = await fetch(`${apiHost}/rest/me`, {
      headers: {
        Cookie: `docent_session_id=${sessionCookie.value}`,
        'Content-Type': 'application/json',
      },
      cache: 'no-store', // Always get fresh auth data
      // Add timeout to prevent hanging requests
      signal: AbortSignal.timeout(5000), // 5 second timeout
    });

    if (!response.ok) {
      return null;
    }

    const user = await response.json();
    return {
      user,
      sessionId: sessionCookie.value,
    };
  } catch (error) {
    console.error('Session verification failed:', error);

    // If it's a connection error, provide helpful guidance
    if (error instanceof Error && error.message.includes('ECONNREFUSED')) {
      console.error('❌ Backend connection refused. Make sure:');
      console.error('   1. Backend service is running');
      console.error('   2. API host environment variables are correctly set');
      console.error('   3. Network connectivity is working');
      console.error(`   INTERNAL_API_HOST: ${process.env.INTERNAL_API_HOST}`);
      console.error(
        `   NEXT_PUBLIC_API_HOST: ${process.env.NEXT_PUBLIC_API_HOST}`
      );
      console.error(`   Using: ${getServerApiHost()}`);
    }

    return null;
  }
});

/**
 * Gets user data - recommended for layouts and components
 * Performs auth check internally via verifySession()
 *
 * Following Next.js best practice: "fetch the user data (getUser()) in the layout
 * and do the auth check in your DAL"
 */
export const getUser = cache(async (): Promise<User | null> => {
  const session = await verifySession();
  if (!session) return null;

  return session.user;
});

/**
 * Requires authentication - redirects to login if not authenticated
 * Use this in page components that require auth
 */
export const requireAuth = cache(async (): Promise<Session> => {
  const session = await verifySession();

  if (!session) {
    redirect('/login');
  }

  return session;
});
