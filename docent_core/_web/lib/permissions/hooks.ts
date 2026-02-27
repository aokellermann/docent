// const useHasCollectionPermission = (collectionId: string, required)

'use client';

import { useParams } from 'next/navigation';

import { PERMISSION_LEVELS, PermissionLevel } from '@/lib/permissions/types';
import { useGetCollectionPermissionsQuery } from './collabSlice';
import { UserPermissions } from '@/app/services/permissionsService';

const hasCollectionPermission = (
  permissions: UserPermissions,
  collectionId: string,
  requiredLevel: PermissionLevel
) => {
  if (!permissions?.collection_permissions) return false;
  const userLevel = permissions.collection_permissions[collectionId] || 'none';
  return PERMISSION_LEVELS[userLevel] >= PERMISSION_LEVELS[requiredLevel];
};

export const useHasCollectionPermission = (
  permission: PermissionLevel,
  collectionIdParam?: string
) => {
  const params = useParams<{ collection_id?: string | string[] }>();
  const routeCollectionId = Array.isArray(params?.collection_id)
    ? params.collection_id[0]
    : params?.collection_id;
  const collectionId = collectionIdParam ?? routeCollectionId;
  const { data: permissions } = useGetCollectionPermissionsQuery(
    collectionId || '',
    { skip: !collectionId }
  );
  if (!permissions || !collectionId) return false;
  return hasCollectionPermission(permissions, collectionId, permission);
};

export const useHasCollectionWritePermission = (collectionIdParam?: string) => {
  return useHasCollectionPermission('write', collectionIdParam);
};

export const useHasCollectionAdminPermission = (collectionIdParam?: string) => {
  return useHasCollectionPermission('admin', collectionIdParam);
};

export const useHasCollectionAdminPermissionForCollection = (
  collectionId: string
) => {
  return useHasCollectionPermission('admin', collectionId);
};
