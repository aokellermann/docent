'use client';

import { useCallback, useEffect, useRef } from 'react';
import { ComplexFilter } from '@/app/types/collectionTypes';
import { FilterListItem } from '@/app/types/filterTypes';
import {
  useUpdateFilterMutation,
  useListFiltersQuery,
} from '@/app/api/filterApi';
import { toast } from 'sonner';
import { getRtkQueryErrorMessage } from '@/lib/rtkQueryError';
import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import {
  setActiveFilterId,
  clearActiveFilterId,
} from '@/app/store/savedFilterSlice';

function filtersEqual(a: ComplexFilter, b: ComplexFilter): boolean {
  return (
    a.op === b.op && JSON.stringify(a.filters) === JSON.stringify(b.filters)
  );
}

interface UseSavedFiltersOptions {
  collectionId: string;
  currentFilter: ComplexFilter | null | undefined;
  onApplyFilter: (filter: ComplexFilter) => void;
}

export function useSavedFilters({
  collectionId,
  currentFilter,
  onApplyFilter,
}: UseSavedFiltersOptions) {
  const dispatch = useAppDispatch();
  const activeFilterId = useAppSelector(
    (state) => state.savedFilter.activeFilterIds[collectionId] ?? null
  );
  const { data: filters } = useListFiltersQuery(collectionId);
  const activeFilter = activeFilterId
    ? (filters?.find((f) => f.id === activeFilterId) ?? null)
    : null;

  const [updateFilter, { isLoading: isUpdating }] = useUpdateFilterMutation();

  // Tracks whether we've applied a filter whose prop update may be async.
  // Prevents the clear-on-empty guard from racing with the prop update.
  const pendingApplyRef = useRef(false);

  const hasActiveConditions =
    currentFilter != null &&
    currentFilter.filters != null &&
    currentFilter.filters.length > 0;

  if (hasActiveConditions && pendingApplyRef.current) {
    pendingApplyRef.current = false;
  }

  useEffect(() => {
    if (
      !hasActiveConditions &&
      activeFilterId !== null &&
      !pendingApplyRef.current
    ) {
      dispatch(clearActiveFilterId(collectionId));
    }
  }, [hasActiveConditions, activeFilterId, dispatch, collectionId]);

  const isDirty =
    activeFilter != null &&
    currentFilter != null &&
    !filtersEqual(currentFilter, activeFilter.filter);

  const handleSelectFilter = useCallback(
    (filter: FilterListItem) => {
      if (isDirty) {
        const confirmed = window.confirm(
          'You have unsaved changes to the current filter. Discard them?'
        );
        if (!confirmed) return;
      }
      dispatch(setActiveFilterId({ collectionId, filterId: filter.id }));
      pendingApplyRef.current = true;
      onApplyFilter(filter.filter);
    },
    [isDirty, onApplyFilter, dispatch, collectionId]
  );

  const handleFilterDeleted = useCallback(
    (filterId: string) => {
      if (activeFilterId === filterId) {
        dispatch(clearActiveFilterId(collectionId));
      }
    },
    [activeFilterId, dispatch, collectionId]
  );

  const handleDeselect = useCallback(() => {
    dispatch(clearActiveFilterId(collectionId));
  }, [dispatch, collectionId]);

  const handleSaveSuccess = useCallback(
    (filter: FilterListItem) => {
      dispatch(setActiveFilterId({ collectionId, filterId: filter.id }));
    },
    [dispatch, collectionId]
  );

  const handleDiscard = useCallback(() => {
    if (!activeFilter) return;
    onApplyFilter(activeFilter.filter);
  }, [activeFilter, onApplyFilter]);

  const handleUpdate = async () => {
    if (!activeFilter || !currentFilter) return;

    try {
      await updateFilter({
        collectionId,
        filterId: activeFilter.id,
        filter: currentFilter,
      }).unwrap();
      toast.success(`Filter "${activeFilter.name || 'Untitled'}" updated`);
    } catch (err) {
      const parsed = getRtkQueryErrorMessage(err, 'Failed to update filter');
      toast.error(parsed.message);
    }
  };

  const saveMode: 'save' | 'save-as' =
    activeFilter != null ? 'save-as' : 'save';

  return {
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
  };
}
