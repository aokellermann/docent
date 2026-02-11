'use client';

import React, { useState } from 'react';
import { ComplexFilter, PrimitiveFilter } from '@/app/types/collectionTypes';
import { FilterControls } from './FilterControls';
import { FilterChips } from './FilterChips';
import { SavedFiltersDropdown } from './SavedFiltersDropdown';
import { SaveFilterPopover } from './SaveFilterDialog';
import { useParams } from 'next/navigation';
import { useFilterFields } from '@/hooks/use-filter-fields';
import { useHasCollectionWritePermission } from '@/lib/permissions/hooks';
import { useSavedFilters } from '@/hooks/use-saved-filters';
import { Bookmark, X, Loader2, Save, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface TranscriptFilterControlsProps {
  metadataData?: Record<string, Record<string, unknown>>;
  baseFilter: ComplexFilter | null | undefined;
  onFiltersChange: (filters: ComplexFilter | null) => void;
}

export const TranscriptFilterControls = ({
  metadataData = {},
  baseFilter,
  onFiltersChange,
}: TranscriptFilterControlsProps) => {
  const params = useParams();
  const collectionId = params.collection_id as string;
  const hasWritePermission = useHasCollectionWritePermission();
  const { fields: agentRunMetadataFields } = useFilterFields({
    collectionId,
    context: { mode: 'agent_runs' },
  });

  const [editingFilter, setEditingFilter] = useState<PrimitiveFilter | null>(
    null
  );

  const handleFiltersChange = (filters: ComplexFilter | null) => {
    onFiltersChange(filters);
    setEditingFilter(null);
  };

  const {
    activeFilterId,
    activeFilter,
    isDirty,
    isUpdating,
    hasActiveConditions,
    saveMode,
    handleSelectFilter,
    handleFilterDeleted,
    handleDeselect,
    handleSaveSuccess,
    handleUpdate,
    handleDiscard,
  } = useSavedFilters({
    collectionId,
    currentFilter: baseFilter,
    onApplyFilter: handleFiltersChange,
  });

  const filterChips = (
    <FilterChips
      filters={baseFilter ?? null}
      onFiltersChange={handleFiltersChange}
      onRequestEdit={setEditingFilter}
    />
  );

  const savedFiltersDropdown = hasWritePermission ? (
    <SavedFiltersDropdown
      collectionId={collectionId}
      activeFilterId={activeFilterId}
      onSelectFilter={handleSelectFilter}
      onFilterDeleted={handleFilterDeleted}
    />
  ) : null;

  return (
    <div className="space-y-1.5">
      <FilterControls
        filters={baseFilter ?? null}
        onFiltersChange={handleFiltersChange}
        metadataFields={agentRunMetadataFields ?? []}
        collectionId={collectionId!}
        metadataData={metadataData}
        initialFilter={editingFilter}
        leadingSlot={savedFiltersDropdown}
      />
      {activeFilter && baseFilter ? (
        <div
          className={`rounded-md border px-2 py-1.5 space-y-1.5 ${
            isDirty
              ? 'bg-orange-bg border-orange-border'
              : 'bg-blue-bg border-blue-border'
          }`}
        >
          <div className="flex items-center gap-2 text-xs">
            <Bookmark
              className={`h-3.5 w-3.5 flex-shrink-0 ${isDirty ? 'text-orange-text' : 'text-blue-text'}`}
            />
            <span
              className={`font-medium truncate ${isDirty ? 'text-orange-text' : 'text-blue-text'}`}
            >
              {activeFilter.name || 'Untitled'}
            </span>
            {isDirty && (
              <>
                <span className="rounded bg-orange-text/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-orange-text flex-shrink-0">
                  Edited
                </span>
                <div className="flex items-center gap-1 ml-auto flex-shrink-0">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px] gap-1 border-orange-border bg-transparent hover:bg-orange-text/10"
                    onClick={handleDiscard}
                    title="Discard changes and revert to saved filter"
                  >
                    <Undo2 className="h-3 w-3" />
                    Discard
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px] gap-1 border-orange-border bg-transparent hover:bg-orange-text/10"
                    onClick={handleUpdate}
                    disabled={isUpdating}
                    title="Save changes to the saved filter"
                  >
                    {isUpdating ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Save className="h-3 w-3" />
                    )}
                    Save
                  </Button>
                  <SaveFilterPopover
                    collectionId={collectionId}
                    currentFilter={baseFilter}
                    disabled={!hasActiveConditions}
                    mode="save-as"
                    onSaveSuccess={handleSaveSuccess}
                    buttonClassName="h-6 text-[11px] border-orange-border bg-transparent hover:bg-orange-text/10"
                    buttonLabel="Save as new"
                  />
                </div>
              </>
            )}
            {!isDirty && (
              <div className="ml-auto flex-shrink-0">
                <button
                  type="button"
                  onClick={handleDeselect}
                  className="rounded-sm p-0.5 hover:bg-blue-text/10 transition-colors"
                  title="Deselect this filter"
                >
                  <X className="h-3.5 w-3.5 text-blue-text" />
                </button>
              </div>
            )}
            {isDirty && (
              <button
                type="button"
                onClick={handleDeselect}
                className="rounded-sm p-0.5 hover:bg-orange-text/10 transition-colors flex-shrink-0"
                title="Deselect this filter"
              >
                <X className="h-3.5 w-3.5 text-orange-text" />
              </button>
            )}
          </div>
          {filterChips}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-1.5">
          {filterChips}
          {hasWritePermission && baseFilter && (
            <SaveFilterPopover
              collectionId={collectionId}
              currentFilter={baseFilter}
              disabled={!hasActiveConditions}
              mode={saveMode}
              onSaveSuccess={handleSaveSuccess}
            />
          )}
        </div>
      )}
    </div>
  );
};
