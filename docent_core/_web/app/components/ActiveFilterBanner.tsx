'use client';

import { Bookmark, X, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FilterListItem } from '@/app/types/filterTypes';
import { ComplexFilter } from '@/app/types/collectionTypes';
import { SaveFilterPopover } from './SaveFilterDialog';

interface ActiveFilterBannerProps {
  activeFilter: FilterListItem;
  isDirty: boolean;
  isUpdating: boolean;
  onDeselect: () => void;
  onUpdate: () => void;
  collectionId: string;
  currentFilter: ComplexFilter;
  hasActiveConditions: boolean;
  onSaveSuccess: (filter: FilterListItem) => void;
}

export function ActiveFilterBanner({
  activeFilter,
  isDirty,
  isUpdating,
  onDeselect,
  onUpdate,
  collectionId,
  currentFilter,
  hasActiveConditions,
  onSaveSuccess,
}: ActiveFilterBannerProps) {
  if (isDirty) {
    return (
      <div className="basis-full flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs bg-orange-bg border-orange-border">
        <Bookmark className="h-3.5 w-3.5 text-orange-text flex-shrink-0" />
        <span className="text-orange-text font-medium truncate">
          Saved filter:
        </span>
        <span className="truncate max-w-[12rem]">
          {activeFilter.name || 'Untitled'}
        </span>
        <span className="rounded bg-orange-text/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-orange-text flex-shrink-0">
          Edited
        </span>
        <div className="flex items-center gap-1 ml-auto flex-shrink-0">
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-[11px] gap-1 border-orange-border bg-transparent hover:bg-orange-text/10"
            onClick={onUpdate}
            disabled={isUpdating}
            title="Update the saved filter with current conditions"
          >
            {isUpdating ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
            Update
          </Button>
          <SaveFilterPopover
            collectionId={collectionId}
            currentFilter={currentFilter}
            disabled={!hasActiveConditions}
            mode="save-as"
            onSaveSuccess={onSaveSuccess}
            buttonClassName="h-6 text-[11px] border-orange-border bg-transparent hover:bg-orange-text/10"
          />
          <button
            type="button"
            onClick={onDeselect}
            className="rounded-sm p-0.5 hover:bg-orange-text/10 transition-colors"
            title="Deselect this filter"
          >
            <X className="h-3.5 w-3.5 text-orange-text" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="basis-full flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs bg-blue-bg border-blue-border">
      <Bookmark className="h-3.5 w-3.5 text-blue-text flex-shrink-0" />
      <span className="text-blue-text font-medium truncate">Saved filter:</span>
      <span className="truncate max-w-[12rem]">
        {activeFilter.name || 'Untitled'}
      </span>
      <button
        type="button"
        onClick={onDeselect}
        className="ml-auto rounded-sm p-0.5 hover:bg-blue-text/10 transition-colors flex-shrink-0"
        title="Deselect this filter"
      >
        <X className="h-3.5 w-3.5 text-blue-text" />
      </button>
    </div>
  );
}
