// const useHasFramegridPermission = (frameGridId: string, required)

import { PERMISSION_LEVELS, PermissionLevel } from "@/lib/permissions/types";
import { usePermissions } from "@/app/contexts/PermissionsContext";
import { useGetFramegridPermissionsQuery } from "./collabSlice";
import { useCallback } from "react";
import { useAppSelector } from "@/app/store/hooks";
import {UserPermissions} from "@/app/services/permissionsService";

const hasFramegridPermission = (permissions: UserPermissions, framegridId: string, requiredLevel: PermissionLevel) => {
    if (!permissions?.framegrid_permissions) return false;
    const userLevel = permissions.framegrid_permissions[framegridId] || 'none';
    return PERMISSION_LEVELS[userLevel] >= PERMISSION_LEVELS[requiredLevel];
}


export const useHasFramegridPermission = (permission: PermissionLevel, fgId?: string) => {
    const framegridId = useAppSelector(state => state.frame.frameGridId) || fgId;
    const {data: permissions} = useGetFramegridPermissionsQuery(framegridId || '');
    if (!permissions || !framegridId) return false;
    return hasFramegridPermission(permissions, framegridId, permission);
}

export const useHasFramegridReadPermission = () => {
    return useHasFramegridPermission("read");
}

export const useHasFramegridWritePermission = () => {
    return useHasFramegridPermission("write");
}


export const useHasFramegridAdminPermission = () => {
    return useHasFramegridPermission("admin");
}