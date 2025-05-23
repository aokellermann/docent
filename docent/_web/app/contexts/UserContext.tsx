'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';

import { apiRestClient } from '../services/apiService';
import type { User } from '../types/userTypes';

type UserContextType = {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  logout: () => Promise<void>;
};

const UserContext = createContext<UserContextType | null>(null);

export const UserProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await apiRestClient.get('/me');
        setUser(response.data);
      } catch (error: any) {
        // If we get a 401, that's expected for users without valid sessions
        if (error.response?.status === 401) {
          setUser(null);
        } else {
          console.error('Error fetching user:', error);
          setUser(null);
        }
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, []);

  const logout = async () => {
    try {
      await apiRestClient.post('/logout');
    } catch (error) {
      console.error('Error during logout:', error);
    } finally {
      // Clear user state regardless of API call success
      setUser(null);
    }
  };

  return (
    <UserContext.Provider value={{ user, loading, setUser, logout }}>
      {children}
    </UserContext.Provider>
  );
};

export const useUser = () => {
  const context = useContext(UserContext);
  if (!context) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};
