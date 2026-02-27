import { useCallback } from 'react';
import { v4 as uuid4 } from 'uuid';
import {
  type CollectionFilter,
  type ComplexFilter,
  type PrimitiveFilter,
} from '@/app/types/collectionTypes';
import { useGetChartMetadataQuery } from '@/app/api/chartApi';
import { usePostBaseFilterMutation } from '@/app/api/collectionApi';

export function useChartFilters(collectionId: string | null | undefined) {
  const [postBaseFilter] = usePostBaseFilterMutation();

  const { data: chartMetadata } = useGetChartMetadataQuery(
    { collectionId: collectionId! },
    { skip: !collectionId }
  );

  const createFilter = useCallback(
    (dimId: string, value: string): PrimitiveFilter | undefined => {
      // Find the dimension in the chart metadata
      const allDimensions = [
        ...(chartMetadata?.dimensions || []),
        ...(chartMetadata?.measures || []),
      ];
      const dimension = allDimensions.find((dim) => dim.key === dimId);

      // We can't filter on anything besides run metadata (for now)
      if (dimension?.kind !== 'run_metadata') {
        return undefined;
      }

      // Build key path from dimension metadata
      const key_path = ['metadata', ...dimension.json_path.split('.')];

      return {
        type: 'primitive',
        key_path,
        value,
        op: '==',
        id: uuid4(),
        name: null,
        supports_sql: true,
      };
    },
    [chartMetadata?.dimensions, chartMetadata?.measures]
  );

  const dedupePrimitiveFilters = useCallback(
    (filters: CollectionFilter[]): CollectionFilter[] => {
      const seenFilterKeys = new Set<string>();
      return filters.reduceRight<CollectionFilter[]>((acc, filter) => {
        if (filter.type !== 'primitive') {
          return [filter, ...acc];
        }

        const keyPath = filter.key_path?.join('.') || '';
        const filterKey = `${keyPath}:${filter.value}:${filter.op}`;
        if (seenFilterKeys.has(filterKey)) {
          return acc;
        }

        seenFilterKeys.add(filterKey);
        return [filter, ...acc];
      }, []);
    },
    []
  );

  const applyFilters = useCallback(
    async (filters: PrimitiveFilter[]) => {
      if (!collectionId || filters.length === 0) {
        return;
      }

      const dedupedFilters = dedupePrimitiveFilters(filters);
      const nextFilter: ComplexFilter = {
        id: uuid4(),
        name: null,
        type: 'complex',
        op: 'and',
        supports_sql: true,
        filters: dedupedFilters,
      };

      try {
        await postBaseFilter({
          collection_id: collectionId,
          filter: nextFilter,
        }).unwrap();
      } catch (error) {
        console.error('Failed to apply chart filter', error);
      }
    },
    [collectionId, dedupePrimitiveFilters, postBaseFilter]
  );

  const handleCellClick = useCallback(
    (
      xKey: string,
      xValue: string,
      seriesKey?: string,
      seriesValue?: string
    ) => {
      if (seriesKey && seriesValue) {
        // 2D case: add both filters
        const xFilter = createFilter(xKey, xValue);
        const seriesFilter = createFilter(seriesKey, seriesValue);
        const validFilters = [xFilter, seriesFilter].filter(
          (f): f is PrimitiveFilter => f !== undefined
        );
        if (validFilters.length > 0) {
          void applyFilters(validFilters);
        }
      } else {
        // 1D case: add single filter
        const filter = createFilter(xKey, xValue);
        if (filter) {
          void applyFilters([filter]);
        }
      }
    },
    [applyFilters, createFilter]
  );

  const handleDimensionClick = useCallback(
    (dimKey: string, dimValue: string) => {
      const filter = createFilter(dimKey, dimValue);
      if (filter) {
        void applyFilters([filter]);
      }
    },
    [applyFilters, createFilter]
  );

  return {
    createFilter,
    handleCellClick,
    handleDimensionClick,
  };
}
