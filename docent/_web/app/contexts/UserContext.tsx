'use client';

import {
  createContext,
  useContext,
  useState,
  useEffect,
  ReactNode,
} from 'react';
import type { User } from '../lib/dal';
import { getCurrentUser } from '../services/authService';

interface UserContextType {
  user: User | null;
  setUser: (user: User | null) => void;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

interface UserProviderProps {
  children: ReactNode;
  user: User | null; // Can be null for non-authenticated pages
}

export const UserProvider = ({
  children,
  user: initialUser,
}: UserProviderProps) => {
  const [user, setUser] = useState<User | null>(initialUser);

  // Validate session on mount to catch stale server-side state
  useEffect(() => {
    // Only validate if we have an initial user from server-side
    if (initialUser) {
      getCurrentUser()
        .then((currentUser) => {
          // If server says no user but we have one, clear it
          if (!currentUser && user) {
            setUser(null);
          }
        })
        .catch(() => {
          // Clear user state on validation error
          if (user) {
            setUser(null);
          }
        });
    }
  }, [initialUser, user]);

  return (
    <UserContext.Provider value={{ user, setUser }}>
      {children}
    </UserContext.Provider>
  );
};

/**
 * Hook for components that may or may not have a user
 * Use this in shared components or pages that handle both states
 */
export const useUser = () => {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};

/**
 * Hook for components that require authentication
 * Throws an error if user is null - use only in authenticated areas
 * This replaces the need for a separate AuthenticatedUserContext
 */
export const useRequireAuth = (): {
  user: User;
  setUser: (user: User) => void;
} => {
  const { user, setUser } = useUser();

  if (!user) {
    throw new Error(
      'useRequireAuth used in component without authenticated user. ' +
        'This hook should only be used in authenticated pages/components.'
    );
  }

  // Type-safe return - user is guaranteed to be non-null
  return {
    user,
    setUser: (newUser: User) => setUser(newUser), // Only allow non-null users
  };
};
