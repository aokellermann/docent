'use client';

import { Layers, Loader2 } from 'lucide-react';
import { useState } from 'react';

import { FrameGrid } from '@/app/types/frameTypes';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { deleteFrameGrid, fetchFrameGrids } from '../store/frameSlice';
import { useAppDispatch } from '../store/hooks';

import FrameGridRow from './FrameGridRow';

interface FrameGridsTableProps {
  frameGrids?: FrameGrid[];
  isLoading: boolean;
}

export function FrameGridsTable({
  frameGrids,
  isLoading,
}: FrameGridsTableProps) {
  const dispatch = useAppDispatch();

  // Delete dialog state – kept here so multiple rows can reuse shared dialog
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [deletingGrid, setDeletingGrid] = useState<FrameGrid | null>(null);

  const openDeleteDialog = (grid: FrameGrid) => {
    setDeletingGrid(grid);
    setIsDeleteDialogOpen(true);
  };

  const handleDeleteFrameGrid = () => {
    if (!deletingGrid) return;

    dispatch(deleteFrameGrid(deletingGrid.id)).then(() => {
      dispatch(fetchFrameGrids());
    });
    setIsDeleteDialogOpen(false);
  };

  if (isLoading || !frameGrids) {
    return (
      <div className="flex-1 flex items-center justify-center h-full min-h-[200px]">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (frameGrids.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 px-3 text-center">
        <div className="bg-secondary p-3 rounded-full mb-3">
          <Layers className="h-7 w-7 text-secondary" />
        </div>
        <h3 className="text-sm font-medium text-primary mb-1">
          No frame grids available
        </h3>
        <p className="text-xs text-muted-foreground max-w-md">
          No frame grids have been created yet. Create a new frame grid to get
          started.
        </p>
      </div>
    );
  }

  return (
    <>
      <Table>
        <TableHeader className="bg-secondary sticky top-0">
          <TableRow>
            <TableHead className="w-[15%] py-2.5 font-medium text-xs text-muted-foreground">
              ID
            </TableHead>
            <TableHead className="w-[25%] py-2.5 font-medium text-xs text-muted-foreground">
              Name
            </TableHead>
            <TableHead className="w-[35%] py-2.5 font-medium text-xs text-muted-foreground">
              Description
            </TableHead>
            <TableHead className="w-[15%] py-2.5 font-medium text-xs text-muted-foreground">
              Created
            </TableHead>
            <TableHead className="w-[10%] py-2.5 font-medium text-xs text-muted-foreground text-right">
              Actions
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {frameGrids.map((grid) => (
            <FrameGridRow
              key={grid.id}
              framegrid={grid}
              onDelete={openDeleteDialog}
            />
          ))}
        </TableBody>
      </Table>

      {/* Delete Confirmation Dialog - keep this one as requested */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Frame Grid</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this frame grid? This action
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            {deletingGrid && (
              <div className="flex flex-col space-y-2 bg-secondary p-3 rounded-md">
                <div className="text-sm font-medium">
                  {deletingGrid.name || 'Unnamed Grid'}
                </div>
                <div className="text-xs text-muted-foreground">
                  {deletingGrid.description || 'No description'}
                </div>
                <div className="text-xs font-mono text-secondary">
                  ID: {deletingGrid.id}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteFrameGrid}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
