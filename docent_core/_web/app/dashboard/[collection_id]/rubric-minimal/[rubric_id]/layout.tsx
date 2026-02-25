'use client';

import React, { Suspense, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import MinimalSingleRubricArea from '../components/MinimalSingleRubricArea';
import { RubricVersionProvider } from '@/providers/use-rubric-version';
import {
  CitationNavigationProvider,
  useCitationNavigation,
} from '@/providers/CitationNavigationProvider';
import { TextSelectionProvider } from '@/providers/use-text-selection';
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable';
import { cn } from '@/lib/utils';
import type { ImperativePanelHandle } from 'react-resizable-panels';

interface RubricMinimalLayoutBodyProps {
  collectionId: string;
  rubricId: string;
  children: React.ReactNode;
}

function RubricMinimalLayoutBody({
  collectionId,
  rubricId,
  children,
}: RubricMinimalLayoutBodyProps) {
  const { agent_run_id: agentRunId, result_id: resultId } = useParams<{
    agent_run_id?: string;
    result_id?: string;
  }>();
  const isOnResultRoute = !!resultId || !!agentRunId;
  const router = useRouter();
  const citationNav = useCitationNavigation();

  useEffect(() => {
    if (!citationNav || agentRunId) return;

    const handler = ({ target }: { target: any; source?: string }) => {
      citationNav.setPendingCitation(target);
      router.push(
        `/dashboard/${collectionId}/rubric-minimal/${rubricId}/agent_run/${target.item.agent_run_id}`
      );
    };
    citationNav.registerHandler(handler);

    return () => citationNav.registerHandler(null);
  }, [citationNav, agentRunId, collectionId, rubricId, router]);

  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);

  // Imperatively resize panels when navigating to/from a result route
  useEffect(() => {
    leftPanelRef.current?.resize(isOnResultRoute ? 50 : 100);
    rightPanelRef.current?.resize(isOnResultRoute ? 50 : 0);
  }, [isOnResultRoute]);

  return (
    <ResizablePanelGroup
      direction="horizontal"
      className="flex-1 flex bg-card space-x-3 min-h-0 shrink-0 border rounded-lg"
    >
      <ResizablePanel
        ref={leftPanelRef}
        defaultSize={100}
        minSize={isOnResultRoute ? 20 : 100}
        maxSize={100}
        className="flex p-3"
      >
        <div className="[&_textarea]:!h-24 [&_textarea]:!max-h-40 flex flex-col flex-1 min-w-0 min-h-0">
          <MinimalSingleRubricArea rubricId={rubricId} />
        </div>
      </ResizablePanel>

      <ResizableHandle
        className={cn('!mx-0 !px-0', !isOnResultRoute && 'hidden')}
      />
      <ResizablePanel
        ref={rightPanelRef}
        defaultSize={0}
        minSize={0}
        maxSize={isOnResultRoute ? 80 : 0}
        className="flex-1 min-w-0 min-h-0 p-3 !mx-0"
      >
        {children}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}

export default function RubricMinimalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { collection_id: collectionId, rubric_id: rubricId } = useParams<{
    collection_id: string;
    rubric_id: string;
  }>();

  return (
    <Suspense>
      <CitationNavigationProvider>
        <RubricVersionProvider rubricId={rubricId} collectionId={collectionId}>
          <TextSelectionProvider>
            <RubricMinimalLayoutBody
              collectionId={collectionId}
              rubricId={rubricId}
            >
              {children}
            </RubricMinimalLayoutBody>
          </TextSelectionProvider>
        </RubricVersionProvider>
      </CitationNavigationProvider>
    </Suspense>
  );
}
