'use client';

import React from 'react';
import { NavigateToCitation } from '@/components/CitationRenderer';

interface CitationNavigationContextValue {
  registerHandler: (handler: NavigateToCitation | null) => void;
  navigateToCitation: NavigateToCitation;
  prepareForNavigation: () => void;
}

const CitationNavigationContext =
  React.createContext<CitationNavigationContextValue | null>(null);

export function useCitationNavigation(): CitationNavigationContextValue | null {
  const ctx = React.useContext(CitationNavigationContext);
  return ctx;
}

export const CitationNavigationProvider: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  const handlerRef = React.useRef<NavigateToCitation | null>(null);
  const pendingRef = React.useRef<{
    args: Parameters<NavigateToCitation>[0];
  } | null>(null);

  const registerHandler = React.useCallback(
    (handler: NavigateToCitation | null) => {
      handlerRef.current = handler;
      if (handler && pendingRef.current) {
        const { args } = pendingRef.current;
        pendingRef.current = null;
        // Defer to let the viewer settle
        requestAnimationFrame(() => handler(args));
      }
    },
    []
  );

  const prepareForNavigation = React.useCallback(() => {
    handlerRef.current = null;
  }, []);

  const navigateToCitation = React.useCallback<NavigateToCitation>(
    ({ citation, newTab }) => {
      const handler = handlerRef.current;
      if (handler) {
        handler({ citation, newTab });
        return;
      }
      // Store pending until a handler registers (e.g., after route change)
      pendingRef.current = { args: { citation, newTab } };
    },
    []
  );

  const value = React.useMemo(
    () => ({ registerHandler, navigateToCitation, prepareForNavigation }),
    [registerHandler, navigateToCitation, prepareForNavigation]
  );

  return (
    <CitationNavigationContext.Provider value={value}>
      {children}
    </CitationNavigationContext.Provider>
  );
};
