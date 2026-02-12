'use client';

import { Bookmark, X, Loader2, Undo2, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FilterListItem } from '@/app/types/filterTypes';
import { ComplexFilter } from '@/app/types/collectionTypes';
import { SaveFilterPopover } from './SaveFilterDialog';

interface ActiveFilterBannerProps {
  activeFilter: FilterListItem;
  isDirty: boolean;
  isUpdating: boolean;
  onDeselect: () => void;
  onDiscard: () => void;
  onUpdate: () => void;
  collectionId: string;
  currentFilter: ComplexFilter;
  hasActiveConditions: boolean;
  onSaveSuccess: (filter: FilterListItem) => void;
  children?: React.ReactNode;
}

export function ActiveFilterBanner({
  activeFilter,
  isDirty,
  isUpdating,
  onDeselect,
  onDiscard,
  onUpdate,
  collectionId,
  currentFilter,
  hasActiveConditions,
  onSaveSuccess,
  children,
}: ActiveFilterBannerProps) {
  return (
    <div
      className={`filter-banner basis-full rounded-md border px-2 py-1.5 space-y-1.5 text-xs ${
        isDirty
          ? 'bg-purple-bg border-purple-border'
          : 'bg-blue-bg border-blue-border'
      }`}
    >
      <div className="flex items-center gap-1.5 min-w-0 min-h-6">
        <Bookmark
          className={`h-3.5 w-3.5 flex-shrink-0 ${isDirty ? 'text-purple-text' : 'text-blue-text'}`}
        />
        {isDirty && (
          <span className="rounded bg-purple-text/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-purple-text flex-shrink-0">
            Edited
          </span>
        )}
        <span
          className={`font-medium truncate min-w-[8ch] ${isDirty ? 'text-purple-text' : 'text-blue-text'}`}
        >
          {activeFilter.name || 'Untitled'}
        </span>
        <div className="flex items-center gap-1 ml-auto flex-shrink-0">
          {isDirty && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-[11px] gap-1 border-purple-border bg-transparent hover:bg-purple-text/10"
                onClick={onDiscard}
                title="Revert to saved filter conditions"
              >
                <Undo2 className="h-3 w-3" />
                <span className="filter-btn-label">Revert</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-[11px] gap-1 border-purple-border bg-transparent hover:bg-purple-text/10"
                onClick={onUpdate}
                disabled={isUpdating}
                title="Save changes to active filter"
              >
                {isUpdating ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                <span className="filter-btn-label">Save</span>
              </Button>
              <SaveFilterPopover
                collectionId={collectionId}
                currentFilter={currentFilter}
                disabled={!hasActiveConditions}
                mode="save-as"
                onSaveSuccess={onSaveSuccess}
                buttonClassName="h-6 text-[11px] gap-1 border-purple-border bg-transparent hover:bg-purple-text/10"
                labelClassName="filter-btn-label text-muted-foreground"
              />
            </>
          )}
          <button
            type="button"
            onClick={onDeselect}
            className={`rounded-sm p-0.5 transition-colors ${
              isDirty ? 'hover:bg-purple-text/10' : 'hover:bg-blue-text/10'
            }`}
            title="Unlink active filter (current conditions stay applied)"
          >
            <X
              className={`h-3.5 w-3.5 ${isDirty ? 'text-purple-text' : 'text-blue-text'}`}
            />
          </button>
        </div>
      </div>
      {children}
    </div>
  );
}
