'use client';

import {
  createContext,
  useContext,
  ReactNode,
  useMemo,
  useCallback,
} from 'react';
import { UserPermissions } from '../services/permissionsService';
import { PERMISSION_LEVELS, PermissionLevel } from '@/lib/permissions/types';

interface PermissionsContextType {
  permissions: UserPermissions | null;
  hasFramegridPermission: (
    frameGridId: string,
    requiredLevel: PermissionLevel
  ) => boolean;
  hasViewPermission: (
    viewId: string,
    requiredLevel: PermissionLevel
  ) => boolean;
  frameGridId: string;
}

const PermissionsContext = createContext<PermissionsContextType | undefined>(
  undefined
);

interface PermissionsProviderProps {
  children: ReactNode;
  frameGridId: string;
  permissions: UserPermissions | null;
}

export const PermissionsProvider = ({
  children,
  frameGridId,
  permissions,
}: PermissionsProviderProps) => {
  const hasFramegridPermission = useCallback(
    (frameGridId: string, requiredLevel: PermissionLevel): boolean => {
      if (!permissions?.framegrid_permissions) return false;

      const userLevel =
        permissions.framegrid_permissions[frameGridId] || 'none';
      return (
        PERMISSION_LEVELS[userLevel as keyof typeof PERMISSION_LEVELS] >=
        PERMISSION_LEVELS[requiredLevel]
      );
    },
    [permissions]
  );

  const hasViewPermission = useCallback(
    (viewId: string, requiredLevel: PermissionLevel): boolean => {
      if (!permissions?.view_permissions) return false;

      const userLevel = permissions.view_permissions[viewId] || 'none';
      return PERMISSION_LEVELS[userLevel] >= PERMISSION_LEVELS[requiredLevel];
    },
    [permissions]
  );

  const contextValue = useMemo(
    () => ({
      permissions,
      hasFramegridPermission,
      hasViewPermission,
      frameGridId,
    }),
    [permissions, hasFramegridPermission, hasViewPermission, frameGridId]
  );

  return (
    <PermissionsContext.Provider value={contextValue}>
      {children}
    </PermissionsContext.Provider>
  );
};

export const usePermissions = () => {
  const context = useContext(PermissionsContext);
  if (context === undefined) {
    throw new Error('usePermissions must be used within a PermissionsProvider');
  }
  return context;
};
