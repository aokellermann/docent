'use client';

import React, { useState } from 'react';
import { ComplexFilter, PrimitiveFilter } from '@/app/types/collectionTypes';
import { FilterControls } from './FilterControls';
import { FilterChips } from './FilterChips';
import { useParams } from 'next/navigation';
import { useFilterFields } from '@/hooks/use-filter-fields';

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

  return (
    <div className="space-y-1.5">
      <FilterControls
        filters={baseFilter ?? null}
        onFiltersChange={handleFiltersChange}
        metadataFields={agentRunMetadataFields ?? []}
        collectionId={collectionId!}
        metadataData={metadataData}
        initialFilter={editingFilter}
      />
      <FilterChips
        filters={baseFilter ?? null}
        onFiltersChange={handleFiltersChange}
        onRequestEdit={setEditingFilter}
        className="mb-1.5"
      />
    </div>
  );
};
