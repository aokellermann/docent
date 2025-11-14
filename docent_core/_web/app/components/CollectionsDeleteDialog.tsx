'use client';

import { Collection } from '@/app/types/collectionTypes';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface CollectionsDeleteDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCollections: Collection[];
  onConfirm: () => Promise<void>;
  isDeleting?: boolean;
}

export function CollectionsDeleteDialog({
  isOpen,
  onOpenChange,
  selectedCollections,
  onConfirm,
  isDeleting = false,
}: CollectionsDeleteDialogProps) {
  const count = selectedCollections.length;
  const isSingle = count === 1;
  const singleCollection = isSingle ? selectedCollections[0] : null;

  const handleConfirm = async () => {
    await onConfirm();
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isSingle ? 'Delete Collection' : 'Delete Collections'}
          </DialogTitle>
          <DialogDescription>
            {isSingle
              ? 'Are you sure you want to delete this collection? This action cannot be undone.'
              : `Are you sure you want to delete ${count} collection${count !== 1 ? 's' : ''}? This action cannot be undone.`}
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          {isSingle && singleCollection ? (
            <div className="flex flex-col space-y-2 bg-secondary p-3 rounded-md">
              <div className="text-sm font-medium break-all">
                {singleCollection.name || 'Unnamed Collection'}
              </div>
              <div className="text-xs text-muted-foreground">
                {singleCollection.description || 'No description'}
              </div>
              <div className="text-xs font-mono text-secondary">
                ID: {singleCollection.id}
              </div>
            </div>
          ) : (
            <div className="flex flex-col space-y-2 bg-secondary p-3 rounded-md max-h-[300px] overflow-y-auto">
              {selectedCollections.map((collection) => (
                <div key={collection.id} className="text-xs">
                  <div className="font-medium">
                    {collection.name || 'Unnamed Collection'}
                  </div>
                  <div className="text-muted-foreground font-mono">
                    {collection.id}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={isDeleting}
          >
            {isSingle
              ? 'Delete'
              : `Delete ${count} ${count !== 1 ? 'Collections' : 'Collection'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
