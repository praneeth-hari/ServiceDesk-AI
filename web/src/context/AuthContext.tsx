import React, { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../api/client';
import { User, TokenResponse } from '../api/types';
import { AuthContext } from './auth-context';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const saved = typeof window !== 'undefined' ? sessionStorage.getItem('user') : null;
    if (saved) {
      try {
        return JSON.parse(saved) as User;
      } catch {
        return null;
      }
    }
    return null;
  });

  const [token, setToken] = useState<string | null>(() => {
    return typeof window !== 'undefined' ? sessionStorage.getItem('access_token') : null;
  });

  const [isLoading, setIsLoading] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const storedToken = sessionStorage.getItem('access_token');
    const storedUser = sessionStorage.getItem('user');
    return Boolean(storedToken && !storedUser);
  });

  // Security trade-off: Storing the JWT token in sessionStorage makes it accessible to client-side
  // JavaScript (vulnerable to XSS if malicious scripts execute), but it restricts the token lifetime
  // strictly to the current browser tab, prevents cross-tab leakage, clears automatically when the tab
  // closes, and eliminates CSRF attack vectors since the browser does not attach it automatically like cookies.
  const logout = useCallback(() => {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('user');
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = sessionStorage.getItem('access_token');
      const storedUser = sessionStorage.getItem('user');
      if (storedToken && !storedUser) {
        try {
          const profile = await apiFetch<User>('/users/me');
          setUser(profile);
          sessionStorage.setItem('user', JSON.stringify(profile));
        } catch {
          logout();
        } finally {
          setIsLoading(false);
        }
      } else {
        setIsLoading(false);
      }
    };

    initAuth();
  }, [logout]);

  const login = async (email: string, password: string) => {
    const tokenData = await apiFetch<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
      skipAuth: true,
    });

    sessionStorage.setItem('access_token', tokenData.access_token);
    setToken(tokenData.access_token);

    const profile = await apiFetch<User>('/users/me');
    sessionStorage.setItem('user', JSON.stringify(profile));
    setUser(profile);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        role: user?.role ?? null,
        token,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
