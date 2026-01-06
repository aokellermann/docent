'use client';

import React from 'react';
import { ChartsArea } from '@/app/components/ChartsArea';

export default function ChartsPage() {
  return (
    <div className="flex-1 flex bg-card min-h-0 shrink-0 border rounded-lg p-3">
      <div className="size-full min-w-0 overflow-auto flex flex-col">
        <div className="flex flex-col mb-2">
          <div className="text-sm font-semibold">Chart Visualization</div>
        </div>
        <ChartsArea />
      </div>
    </div>
  );
}
