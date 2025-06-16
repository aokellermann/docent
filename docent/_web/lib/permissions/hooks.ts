// const useHasFramegridPermission = (frameGridId: string, required)

import { PermissionLevel } from "@/lib/permissions/types";
import { usePermissions } from "@/app/contexts/PermissionsContext";

export const useHasFramegridPermission = (permission: PermissionLevel) => {
    const { frameGridId, hasFramegridPermission } = usePermissions();
    return hasFramegridPermission(frameGridId, permission);
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