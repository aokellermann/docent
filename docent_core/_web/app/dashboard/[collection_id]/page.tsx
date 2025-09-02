'use client';

import React, { Suspense } from 'react';

import ExperimentViewer from '../../components/ExperimentViewer';
import RubricArea from '@/app/dashboard/[collection_id]/components/RubricArea';

export default function DocentDashboard() {
  return (
    <Suspense>
      <div className="flex-1 flex space-x-3 min-h-0">
        <div className="flex-1 min-h-0 overflow-hidden">
          <ExperimentViewer />
        </div>
        <RubricArea />
        {/* <SearchArea /> */}
      </div>
      {/* <Dashboard /> */}
    </Suspense>
  );
}
