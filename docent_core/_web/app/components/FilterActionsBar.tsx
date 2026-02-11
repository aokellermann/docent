'use client';

import { ComplexFilter } from '@/app/types/collectionTypes';
import { SaveFilterPopover } from './SaveFilterDialog';
import { SavedFiltersDropdown } from './SavedFiltersDropdown';

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
  const hasActiveFilter =
    currentFilter && currentFilter.filters && currentFilter.filters.length > 0;

  return (
    <div className="flex items-center gap-1.5">
      <SavedFiltersDropdown
        collectionId={collectionId}
        onApplyFilter={onApplyFilter}
      />
      {currentFilter && (
        <SaveFilterPopover
          collectionId={collectionId}
          currentFilter={currentFilter}
          disabled={!hasActiveFilter}
        />
      )}
    </div>
  );
}
