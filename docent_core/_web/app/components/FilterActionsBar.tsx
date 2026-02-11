'use client';

import { ComplexFilter } from '@/app/types/collectionTypes';
import { SaveFilterPopover } from './SaveFilterDialog';
import { SavedFiltersDropdown } from './SavedFiltersDropdown';
import { ActiveFilterBanner } from './ActiveFilterBanner';
import { useSavedFilters } from '@/hooks/use-saved-filters';

interface FilterActionsBarProps {
  collectionId: string;
  currentFilter: ComplexFilter | null | undefined;
  onApplyFilter: (filter: ComplexFilter) => void;
}

export function FilterActionsBar({
  collectionId,
  currentFilter,
  onApplyFilter,
}: FilterActionsBarProps) {
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
  } = useSavedFilters({ collectionId, currentFilter, onApplyFilter });

  return (
    <>
      {activeFilter && currentFilter && (
        <ActiveFilterBanner
          activeFilter={activeFilter}
          isDirty={isDirty}
          isUpdating={isUpdating}
          onDeselect={handleDeselect}
          onUpdate={handleUpdate}
          collectionId={collectionId}
          currentFilter={currentFilter}
          hasActiveConditions={hasActiveConditions}
          onSaveSuccess={handleSaveSuccess}
        />
      )}
      <div className="flex flex-wrap items-center gap-1.5 min-w-0">
        <SavedFiltersDropdown
          collectionId={collectionId}
          activeFilterId={activeFilterId}
          onSelectFilter={handleSelectFilter}
          onFilterDeleted={handleFilterDeleted}
        />
        {(!isDirty || !activeFilter) && currentFilter && (
          <SaveFilterPopover
            collectionId={collectionId}
            currentFilter={currentFilter}
            disabled={!hasActiveConditions}
            mode={saveMode}
            onSaveSuccess={handleSaveSuccess}
          />
        )}
      </div>
    </>
  );
}
