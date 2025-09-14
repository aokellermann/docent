'use client';

import { useParams } from 'next/navigation';
import React, { Suspense, useRef } from 'react';

import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import { setAgentRunSidebarTab } from '@/app/store/transcriptSlice';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import AgentSummary from '../components/AgentSummary';
import AgentRunViewer, {
  AgentRunViewerHandle,
} from '../components/AgentRunViewer';
import TranscriptChat from '@/components/TranscriptChat';
import { Citation } from '@/app/types/experimentViewerTypes';

export default function AgentRunPage() {
  const dispatch = useAppDispatch();

  const collectionId = useAppSelector(
    (state) => state.collection?.collectionId
  );
  const rightSidebarOpen = useAppSelector(
    (state) => state.transcript?.rightSidebarOpen
  );
  const selectedTab = useAppSelector(
    (state) => state.transcript?.agentRunSidebarTab ?? 'chat'
  );

  const params = useParams();
  const curAgentRunId = Array.isArray(params.agent_run_id)
    ? params.agent_run_id[0]
    : params.agent_run_id;

  const agentRunViewerRef = useRef<AgentRunViewerHandle>(null);

  /**
   * TODO(mengk): fix, this is known to be broken.
   */

  // const alreadyScrolledRef = useRef(false);
  //  const searchParams = useSearchParams();
  // const blockIdxParam = searchParams.get('block_idx');
  // const blockIdx = blockIdxParam ? parseInt(blockIdxParam, 10) : undefined;
  // const transcriptIdxParam = searchParams.get('transcript_idx');
  // const transcriptIdx = transcriptIdxParam
  //   ? parseInt(transcriptIdxParam, 10)
  //   : undefined;
  // useEffect(() => {
  //   if (
  //     blockIdx !== undefined &&
  //     agentRunViewerRef.current &&
  //     !alreadyScrolledRef.current
  //   ) {
  //     alreadyScrolledRef.current = true;
  //     console.log('scrolling to block', blockIdx);
  //     agentRunViewerRef.current?.scrollToBlock(
  //       blockIdx,
  //       transcriptIdx || 0,
  //       0,
  //       undefined
  //     );
  //   }
  // }, [blockIdx]);

  const onShowAgentRun = (
    agentRunId: string,
    blockIdx?: number,
    transcriptIdx?: number,
    highlightDuration?: number,
    citation?: Citation
  ) => {
    if (agentRunId !== curAgentRunId) {
      console.error(
        'this should never happen; why is the chat agent requesting a different agent run?'
      );
      return;
    }

    if (blockIdx !== undefined) {
      agentRunViewerRef.current?.scrollToBlock(
        blockIdx,
        transcriptIdx || 0,
        0,
        highlightDuration,
        citation
      );
    }
  };

  return (
    <Suspense>
      {/* Transcript */}
      <Card
        className="h-full basis-1/2 p-3 min-h-0 min-w-0 flex flex-col space-y-2"
        style={{ flexGrow: '2' }}
      >
        <AgentRunViewer agentRunId={curAgentRunId} ref={agentRunViewerRef} />
      </Card>

      {/* Assistant summary / transcript chat */}
      {rightSidebarOpen && (
        <Card className="shrink-0 grow-1 h-full p-3 flex flex-col min-w-0 min-h-0 bg-background basis-2/5">
          <Tabs
            value={selectedTab}
            onValueChange={(value) => dispatch(setAgentRunSidebarTab(value))}
            className="h-full flex flex-col"
          >
            <TabsList className="grid w-full grid-cols-2 h-8">
              <TabsTrigger value="agent" className="text-xs">
                Summary
              </TabsTrigger>
              <TabsTrigger value="chat" className="text-xs">
                Chat
              </TabsTrigger>
            </TabsList>

            <TabsContent value="agent" className="flex-1 mt-0 min-h-0">
              <ScrollArea className="h-full pt-2">
                <AgentSummary onCitationClick={onShowAgentRun} />
              </ScrollArea>
            </TabsContent>

            <TabsContent value="chat" className="flex-1 mt-0 min-h-0">
              <div className="h-full pt-2 flex flex-col min-h-0">
                <TranscriptChat
                  runId={curAgentRunId}
                  collectionId={collectionId}
                  title="Transcript Chat"
                  className="flex-1 flex flex-col min-w-0 min-h-0"
                  onNavigateToCitation={({ citation }) => {
                    if (onShowAgentRun && citation.block_idx !== undefined) {
                      onShowAgentRun(
                        curAgentRunId,
                        citation.block_idx,
                        citation.transcript_idx || 0,
                        500,
                        citation
                      );
                    }
                  }}
                />
              </div>
            </TabsContent>
          </Tabs>
        </Card>
      )}
    </Suspense>
  );
}
