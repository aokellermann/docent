'use client';

import {
  CalendarIcon,
  CheckIcon,
  ClipboardCopyIcon,
  Layers,
  Loader2,
  Pencil,
  Trash2,
  XIcon,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  useReactTable,
  type RowSelectionState,
} from '@tanstack/react-table';

import { BASE_DOCENT_PATH } from '@/app/constants';
import { Collection } from '@/app/types/collectionTypes';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from '@/hooks/use-toast';
import { cn, copyToClipboard } from '@/lib/utils';
import {
  useBulkDeleteCollectionsMutation,
  useDeleteCollectionMutation,
  useGetCollectionsPageQuery,
  useUpdateCollectionMutation,
} from '../api/collectionApi';
import { useGetCollectionsPermissionsQuery } from '@/lib/permissions/collabSlice';
import { PERMISSION_LEVELS, PermissionLevel } from '@/lib/permissions/types';
import { CollectionTablePagination } from './CollectionTablePagination';
import { CollectionsDeleteDialog } from './CollectionsDeleteDialog';

interface CollectionsTableProps {
  // Keep for backward compatibility, but will use paginated endpoint internally
  collections?: Collection[];
  isLoading?: boolean;
}

interface CollectionWithPermissions extends Collection {
  hasWritePermission: boolean;
  hasAdminPermission: boolean;
  permissionsLoading: boolean;
  permissionLevel: PermissionLevel;
}

const PAGE_SIZE = 25;

// Separate components for editable cells to properly use hooks
interface EditableCellProps {
  collection: CollectionWithPermissions;
  isEditing: boolean;
  editingValuesRef: React.MutableRefObject<{
    name: string;
    description: string;
  }>;
}

function EditableNameCell({
  collection,
  isEditing,
  editingValuesRef,
}: EditableCellProps) {
  const [value, setValue] = useState(collection.name ?? '');

  useEffect(() => {
    if (isEditing) {
      setValue(collection.name ?? '');
    }
  }, [isEditing, collection.name]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    editingValuesRef.current.name = newValue;
  };

  return (
    <div onClick={isEditing ? (e) => e.stopPropagation() : undefined}>
      {isEditing ? (
        <Input
          value={value}
          onChange={handleChange}
          placeholder="Enter collection name"
          className="h-7 text-xs py-0 px-2"
        />
      ) : (
        <span className="text-primary text-xs">
          {collection.name || (
            <span className="italic text-secondary">Unnamed Collection</span>
          )}
        </span>
      )}
    </div>
  );
}

function EditableDescriptionCell({
  collection,
  isEditing,
  editingValuesRef,
}: EditableCellProps) {
  const [value, setValue] = useState(collection.description ?? '');

  useEffect(() => {
    if (isEditing) {
      setValue(collection.description ?? '');
    }
  }, [isEditing, collection.description]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setValue(newValue);
    editingValuesRef.current.description = newValue;
  };

  return (
    <div onClick={isEditing ? (e) => e.stopPropagation() : undefined}>
      {isEditing ? (
        <Input
          value={value}
          onChange={handleChange}
          placeholder="Enter description"
          className="h-7 text-xs py-0 px-2"
        />
      ) : (
        <span className="text-xs text-muted-foreground">
          {collection.description || (
            <span className="italic text-muted-foreground">
              No description provided
            </span>
          )}
        </span>
      )}
    </div>
  );
}

export function CollectionsTable({
  collections: _legacyCollections,
  isLoading: _legacyIsLoading,
}: CollectionsTableProps) {
  const router = useRouter();

  // Pagination state
  const [page, setPage] = useState(1);

  // Row selection state
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  // Delete dialog state
  const [deleteDialogState, setDeleteDialogState] = useState<{
    isOpen: boolean;
    collections: Collection[];
  }>({
    isOpen: false,
    collections: [],
  });

  // Editing state per row - only track which row, not the values
  const [editingRowId, setEditingRowId] = useState<string | null>(null);
  // Store the editing values in a ref that gets passed to save handler
  const editingValuesRef = useRef<{ name: string; description: string }>({
    name: '',
    description: '',
  });

  // Fetch paginated collections
  const { data: paginatedData, isLoading } = useGetCollectionsPageQuery({
    page,
    page_size: PAGE_SIZE,
  });

  // Reset row selection when page changes
  useEffect(() => {
    setRowSelection({});
  }, [page]);

  const collections = paginatedData?.items || [];
  const total = paginatedData?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Clamp the page to the total number of pages
  // E.g. if on the top page and all collections are deleted
  useEffect(() => {
    if (!isLoading && collections.length === 0 && total > 0 && page > 1) {
      setPage(Math.min(page, Math.max(1, totalPages)));
    }
  }, [collections.length, total, page, totalPages, isLoading]);

  // Fetch permissions for current page
  const ids = collections.map((c) => c.id);
  const { data: batchPerms, isFetching: permissionsFetching } =
    useGetCollectionsPermissionsQuery(ids, {
      skip: ids.length === 0,
    });

  // Mutations
  const [deleteCollection] = useDeleteCollectionMutation();
  const [bulkDeleteCollections] = useBulkDeleteCollectionsMutation();
  const [updateCollection] = useUpdateCollectionMutation();

  // Prepare collections with permissions
  const collectionsWithPerms: CollectionWithPermissions[] = useMemo(() => {
    return collections.map((collection) => {
      const level: PermissionLevel =
        batchPerms?.collection_permissions?.[collection.id] || 'read';
      const hasWritePermission =
        PERMISSION_LEVELS[level] >= PERMISSION_LEVELS.write;
      const hasAdminPermission =
        PERMISSION_LEVELS[level] >= PERMISSION_LEVELS.admin;
      return {
        ...collection,
        hasWritePermission,
        hasAdminPermission,
        permissionsLoading: Boolean(!batchPerms || permissionsFetching),
        permissionLevel: level,
      };
    });
  }, [collections, batchPerms, permissionsFetching]);

  // Get selected collection IDs that have admin permission
  const selectedCollectionIds = useMemo(() => {
    return Object.keys(rowSelection)
      .filter((id) => rowSelection[id])
      .map((id) => collectionsWithPerms[parseInt(id)]?.id)
      .filter((id) => {
        const collection = collectionsWithPerms.find((c) => c.id === id);
        return collection?.hasAdminPermission;
      });
  }, [rowSelection, collectionsWithPerms]);

  // Handlers
  const openDeleteDialog = (collection: Collection) => {
    setDeleteDialogState({
      isOpen: true,
      collections: [collection],
    });
  };

  const openBulkDeleteDialog = () => {
    const selectedCollections = selectedCollectionIds
      .map((id) => collections.find((c) => c.id === id))
      .filter((c): c is Collection => c !== undefined);

    setDeleteDialogState({
      isOpen: true,
      collections: selectedCollections,
    });
  };

  const handleDeleteConfirm = async () => {
    const collectionIds = deleteDialogState.collections.map((c) => c.id);
    if (collectionIds.length === 0) return;

    const isSingle = collectionIds.length === 1;

    try {
      if (isSingle) {
        await deleteCollection(collectionIds[0]).unwrap();
        setDeleteDialogState({ isOpen: false, collections: [] });
        setRowSelection({});
        toast({
          title: 'Collection Deleted',
          description: 'The collection has been deleted successfully',
        });
      } else {
        const result = await bulkDeleteCollections({
          collection_ids: collectionIds,
        }).unwrap();

        setDeleteDialogState({ isOpen: false, collections: [] });
        setRowSelection({});

        if (result.success) {
          toast({
            title: 'Collections Deleted',
            description: result.message,
          });
        } else {
          toast({
            title: 'Error',
            description: result.message,
            variant: 'destructive',
          });
        }
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: `Failed to delete collection${isSingle ? '' : 's'}`,
        variant: 'destructive',
      });
    }
  };

  const startEditing = (collection: Collection) => {
    setEditingRowId(collection.id);
    editingValuesRef.current = {
      name: collection.name ?? '',
      description: collection.description ?? '',
    };
  };

  const cancelEditing = () => {
    setEditingRowId(null);
  };

  const saveEditing = async (collectionId: string) => {
    try {
      await updateCollection({
        collection_id: collectionId,
        name: editingValuesRef.current.name,
        description: editingValuesRef.current.description,
      }).unwrap();

      toast({
        title: 'Collection Updated',
        description: 'The collection has been updated successfully',
      });

      cancelEditing();
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to update collection',
        variant: 'destructive',
      });
    }
  };

  const copyId = async (collectionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const success = await copyToClipboard(collectionId);
    if (success) {
      toast({
        title: 'Collection ID Copied',
        description: `Copied ${collectionId} to clipboard`,
      });
    } else {
      toast({
        title: 'Failed to copy',
        description: 'Could not copy to clipboard',
        variant: 'destructive',
      });
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString + 'Z');
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const openCollection = (collectionId: string, e?: React.MouseEvent) => {
    if (editingRowId === collectionId) return;
    const href = `${BASE_DOCENT_PATH}/${collectionId}`;
    if (e && (e.metaKey || e.ctrlKey)) {
      window.open(href, '_blank');
      return;
    }
    router.push(href);
  };

  // Table columns
  const columns = useMemo<ColumnDef<CollectionWithPermissions>[]>(() => {
    return [
      {
        id: 'select',
        header: () => null,
        cell: ({ row, table }) => {
          const isSelected = row.getIsSelected();
          const canSelect = row.original.hasAdminPermission;
          if (!canSelect) {
            return null;
          }
          return (
            <Checkbox
              checked={isSelected}
              onCheckedChange={(value) => {
                row.toggleSelected(!!value);
              }}
              aria-label="Select row"
              className="translate-y-[2px] shadow-none border-muted-foreground/40 data-[state=checked]:bg-muted-foreground/20 data-[state=checked]:border-muted-foreground/40 data-[state=checked]:text-muted-foreground"
              onClick={(e) => e.stopPropagation()}
            />
          );
        },
        enableSorting: false,
        size: 40,
      },
      {
        accessorKey: 'id',
        header: 'ID',
        cell: ({ row }) => {
          const collection = row.original;
          return (
            <div className="flex items-center">
              <span className="font-mono text-primary text-xs">
                {collection.id.split('-')[0]}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 ml-1"
                onClick={(e) => copyId(collection.id, e)}
                title="Copy full ID"
              >
                <ClipboardCopyIcon className="h-3 w-3 text-muted-foreground group-hover:text-blue-text" />
              </Button>
            </div>
          );
        },
        size: 150,
      },
      {
        accessorKey: 'name',
        header: 'Name',
        cell: ({ row }) => {
          const collection = row.original;
          const isEditing = editingRowId === collection.id;
          return (
            <EditableNameCell
              collection={collection}
              isEditing={isEditing}
              editingValuesRef={editingValuesRef}
            />
          );
        },
        size: 250,
      },
      {
        accessorKey: 'description',
        header: 'Description',
        cell: ({ row }) => {
          const collection = row.original;
          const isEditing = editingRowId === collection.id;
          return (
            <EditableDescriptionCell
              collection={collection}
              isEditing={isEditing}
              editingValuesRef={editingValuesRef}
            />
          );
        },
        size: 350,
      },
      {
        accessorKey: 'created_at',
        header: 'Created',
        cell: ({ row }) => {
          const collection = row.original;
          return (
            <div className="flex items-center text-muted-foreground">
              <CalendarIcon className="h-3 w-3 mr-1 text-muted-foreground" />
              <span className="text-xs">
                {formatDate(collection.created_at)}
              </span>
            </div>
          );
        },
        size: 150,
      },
      {
        accessorKey: 'permissionLevel',
        header: 'Permission',
        cell: ({ row }) => {
          const collection = row.original;
          if (collection.permissionsLoading) {
            return (
              <Loader2
                size={14}
                className="animate-spin text-muted-foreground"
              />
            );
          }
          const level = collection.permissionLevel;

          const levelLabels = {
            admin: 'Admin',
            write: 'Write',
            read: 'Read',
            none: 'No access',
          };
          return (
            <div
              className={cn(
                'inline-flex items-center px-2 py-0.5 text-muted-foreground text-xs'
              )}
            >
              {levelLabels[level]}
            </div>
          );
        },
        size: 100,
      },
      {
        id: 'actions',
        header: () => <div className="text-right">Actions</div>,
        cell: ({ row }) => {
          const collection = row.original;
          const isEditing = editingRowId === collection.id;
          return (
            <div
              className="flex items-center justify-end space-x-1"
              onClick={(e) => e.stopPropagation()}
            >
              {isEditing ? (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-green-foreground"
                    onClick={() => saveEditing(collection.id)}
                    title="Save changes"
                  >
                    <CheckIcon className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground"
                    onClick={cancelEditing}
                    title="Cancel editing"
                  >
                    <XIcon className="h-3.5 w-3.5" />
                  </Button>
                </>
              ) : collection.permissionsLoading ? (
                <Loader2
                  size={16}
                  className="animate-spin text-muted-foreground"
                />
              ) : collection.hasWritePermission ? (
                <div className="flex items-center gap-3">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-auto w-auto text-muted-foreground group-hover:text-blue-text p-0"
                    onClick={() => startEditing(collection)}
                    disabled={!collection.hasWritePermission}
                    title="Edit collection"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-auto w-auto text-muted-foreground group-hover:text-red-text p-0"
                    disabled={!collection.hasAdminPermission}
                    onClick={() => openDeleteDialog(collection)}
                    title="Delete collection"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : null}
            </div>
          );
        },
        enableSorting: false,
        size: 100,
      },
    ];
  }, [editingRowId]);

  const table = useReactTable({
    data: collectionsWithPerms,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    manualPagination: true,
    pageCount: totalPages,
    state: {
      rowSelection,
    },
    onRowSelectionChange: setRowSelection,
  });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center h-full min-h-[200px]">
        <Loader2 size={16} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (collections.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 px-3 text-center">
        <div className="bg-secondary p-3 rounded-full mb-3">
          <Layers className="h-7 w-7 text-primary" />
        </div>
        <h3 className="text-sm font-medium text-primary mb-1">
          No collections available
        </h3>
        <p className="text-xs text-muted-foreground max-w-md">
          Create a new collection to get started.
        </p>
      </div>
    );
  }

  return (
    <>
      {/* Bulk delete banner - only visible when items are selected */}
      {selectedCollectionIds.length > 0 && (
        <div className="flex items-center justify-between bg-secondary border border-border rounded-md py-1 px-2 mb-3">
          <div className="flex items-center gap-2">
            {/* Select All Checkbox */}
            <Checkbox
              checked={
                table.getIsAllPageRowsSelected() ||
                (table.getIsSomePageRowsSelected() && 'indeterminate')
              }
              onCheckedChange={(value) => {
                // If some rows are selected (indeterminate state), deselect all
                // Otherwise, toggle between select all and deselect all
                const newSelection: RowSelectionState = {};
                if (value && !table.getIsSomePageRowsSelected()) {
                  // Select all rows with admin permission
                  table.getRowModel().rows.forEach((row, index) => {
                    if (row.original.hasAdminPermission) {
                      newSelection[index] = true;
                    }
                  });
                }
                // If value is false or we're in indeterminate state, newSelection stays empty (deselect all)
                table.setRowSelection(newSelection);
              }}
              aria-label="Select all"
              className="border-muted-foreground/40 shadow-none data-[state=checked]:bg-muted-foreground/20 data-[state=checked]:border-muted-foreground/40 data-[state=checked]:text-muted-foreground data-[state=indeterminate]:bg-muted-foreground/20 data-[state=indeterminate]:border-muted-foreground/40 data-[state=indeterminate]:text-muted-foreground"
            />
            {/* Selection count */}
            <span className="text-xs text-muted-foreground">
              {selectedCollectionIds.length} collection
              {selectedCollectionIds.length !== 1 ? 's' : ''} selected
            </span>
          </div>
          {/* Delete button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={openBulkDeleteDialog}
            className="h-7 text-muted-foreground hover:text-red-text p-0"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}

      {/* Table */}
      <Table>
        <TableHeader className="bg-secondary sticky top-0">
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead
                  key={header.id}
                  className="font-medium text-xs text-muted-foreground"
                  style={{ width: header.getSize() }}
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => {
            const collection = row.original;
            const isEditing = editingRowId === collection.id;
            return (
              <TableRow
                key={row.id}
                onClick={(e) => openCollection(collection.id, e)}
                onAuxClick={(e) => {
                  if (e.button === 1) {
                    const href = `${BASE_DOCENT_PATH}/${collection.id}`;
                    window.open(href, '_blank');
                  }
                }}
                className={cn(
                  'group transition-colors cursor-pointer hover:bg-secondary/50 h-11',
                  isEditing && 'bg-blue-50 cursor-default'
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    style={{ width: cell.column.getSize() }}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {/* Pagination in bottom right */}
      <div className="flex justify-end">
        <CollectionTablePagination
          page={page}
          pageSize={PAGE_SIZE}
          totalItems={total}
          setPage={setPage}
        />
      </div>

      {/* Delete dialog (handles both single and bulk) */}
      <CollectionsDeleteDialog
        isOpen={deleteDialogState.isOpen}
        onOpenChange={(open) =>
          setDeleteDialogState((prev) => ({ ...prev, isOpen: open }))
        }
        selectedCollections={deleteDialogState.collections}
        onConfirm={handleDeleteConfirm}
      />
    </>
  );
}
