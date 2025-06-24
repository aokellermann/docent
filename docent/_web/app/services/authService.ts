import { apiRestClient } from './apiService';

/**
 * Pure authentication API operations
 * No side effects (redirects, state management) - just API calls
 */
export class AuthService {
  /**
   * Login user with email
   */
  static async login(
    email: string
  ): Promise<{ id: string; email: string; is_anonymous: boolean }> {
    const response = await apiRestClient.post('/login', { email });
    return response.data;
  }

  /**
   * Signup new user with email
   */
  static async signup(
    email: string
  ): Promise<{ id: string; email: string; is_anonymous: boolean }> {
    const response = await apiRestClient.post('/signup', { email });
    return response.data;
  }

  /**
   * Logout current user (API call only)
   */
  static async logout(): Promise<void> {
    await apiRestClient.post('/logout');
  }
}

// Export convenience functions for easier imports
export const { login, logout, signup } = AuthService;
