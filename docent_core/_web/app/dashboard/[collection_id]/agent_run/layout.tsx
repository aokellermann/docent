'use client';

import React, { Suspense } from 'react';

import ExperimentViewer from '../../../components/ExperimentViewer';
import { useParams } from 'next/navigation';

export default function AgentRunLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const agentRunId = params.agent_run_id as string;
  return (
    <Suspense>
      <div className="flex-1 flex space-x-3 min-h-0">
        <div
          className="basis-96 shrink-0 min-w-0 overflow-hidden"
          style={{ flexGrow: '1' }}
        >
          <ExperimentViewer activeRunId={agentRunId} />
        </div>
        {children}
      </div>
    </Suspense>
  );
}
