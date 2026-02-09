import { User } from '@/app/types/userTypes';
import { cookies, headers } from 'next/headers';
import { COOKIE_KEY, INTERNAL_BASE_URL } from '../constants';

/**
 * Verifies the session with the backend
 * Returns the user and sessionId if valid, otherwise returns null
 */
export async function getUser(): Promise<User | null> {
  // First, check if middleware provided user data via headers
  const headerStore = await headers();
  const middlewareUser = headerStore.get('x-middleware-user');
  if (middlewareUser) {
    try {
      return JSON.parse(middlewareUser);
    } catch (error) {
      console.error('Failed to parse middleware user data:', error);
    }
  }

  // Fallback to normal cookie-based authentication
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get(COOKIE_KEY);

  if (!sessionCookie?.value) {
    return null;
  }

  try {
    const response = await fetch(`${INTERNAL_BASE_URL}/rest/me`, {
      headers: {
        Cookie: `${COOKIE_KEY}=${sessionCookie.value}`,
        'Content-Type': 'application/json',
      },
      cache: 'no-store', // Always get fresh auth data
      // Add timeout to prevent hanging requests
      signal: AbortSignal.timeout(9000), // 9 second timeout
    });
    if (!response.ok) {
      return null;
    }

    const user = await response.json();
    return user;
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    console.error(
      '[getUser]',
      JSON.stringify({
        message: err.message,
        name: err.name,
        stack: err.stack,
      })
    );
    return null;
  }
}
