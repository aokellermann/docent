'use client';

import { useParams, useSearchParams } from 'next/navigation';
import React, { Suspense, useEffect, useRef, useCallback } from 'react';

import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import { getCurAgentRun, getAltAgentRun } from '@/app/store/transcriptSlice';

import TranscriptViewer, {
  TranscriptViewerHandle,
} from '../../transcript/components/TranscriptViewer';
import DiffPanel from './components/DiffPanel';

const SCROLL_DELAY = 250;

export default function AgentRunPage2() {
  const dispatch = useAppDispatch();

  const frameGridId = useAppSelector((state) => state.frame.frameGridId);
  const curAgentRun = useAppSelector((state) => state.transcript.curAgentRun);
  const altAgentRun = useAppSelector((state) => state.transcript.altAgentRun);

  const params = useParams();
  const searchParams = useSearchParams();
  const agentRunIdRaw = params.concat_run_id;
  const blockIdParam = searchParams.get('block_id');
  const blockId = blockIdParam ? parseInt(blockIdParam, 10) : undefined;

  const agentRunIds = React.useMemo(() => {
    return (Array.isArray(agentRunIdRaw) ? agentRunIdRaw[0] : agentRunIdRaw).split('___');
  }, [agentRunIdRaw]);

  /**
   * Handle scrolling to the block
   */

  const transcriptViewerRef = useRef<TranscriptViewerHandle>(null);
  const altTranscriptViewerRef = useRef<TranscriptViewerHandle>(null);

  const alreadyScrolledRef = useRef(false);
  const hasInitAttributeDimId = useAppSelector(
    (state) => state.frame.hasInitAttributeDimId
  );
  const attributeMap = useAppSelector(
    (state) => state.attributeFinder.attributeMap
  );
  useEffect(() => {
    if (alreadyScrolledRef.current) return;

    // We wait until hasInitAttributeDimId is known before continuing
    if (hasInitAttributeDimId === undefined) return;
    // If there is an initial attributeDimId, then we wait until the attributes have populated
    if (hasInitAttributeDimId === true && !attributeMap) return;
    // Else, if it's false, then we don't need to wait

    if (
      transcriptViewerRef.current &&
      curAgentRun?.id === agentRunIds[0] &&
      blockId
    ) {
      alreadyScrolledRef.current = true;
      setTimeout(() => {
        console.log('Scrolling to block', blockId);
        transcriptViewerRef.current?.scrollToBlock(blockId);
      }, 100); // Small delay to allow for DOM rendering
    }
  }, [curAgentRun, blockId, agentRunIds, hasInitAttributeDimId, attributeMap]);

  /**
   * Fetch agent run once
   */

  const fetchRef = useRef(false);
  useEffect(() => {
    if (fetchRef.current || frameGridId === undefined) return;
    if (curAgentRun?.id !== agentRunIds[0] || altAgentRun?.id !== agentRunIds[1]) {
      dispatch(getCurAgentRun(agentRunIds[0]));
      dispatch(getAltAgentRun(agentRunIds[1]));
      fetchRef.current = true;
    }
  }, [frameGridId, agentRunIds, blockId, dispatch, curAgentRun?.id, altAgentRun?.id]);

  const handleShowAgentRun = (agentRunId: string, blockId?: number) => {
    if (agentRunId !== curAgentRun?.id) {
      dispatch(getCurAgentRun(agentRunId));
    }

    if (blockId) {
      setTimeout(() => {
        transcriptViewerRef.current?.scrollToBlock(blockId);
      }, SCROLL_DELAY); // Small delay to allow the transcript to load before scrolling
    }
  };

  // Create a unified scroll function for the DiffPanel that can handle both transcripts
  const handleDiffScrollToBlock = useCallback((blockIndex: number, transcriptIdx?: number) => {
    if (transcriptIdx === 0 && transcriptViewerRef.current) {
      transcriptViewerRef.current.scrollToBlock(blockIndex);
    } else if (transcriptIdx === 1 && altTranscriptViewerRef.current) {
      altTranscriptViewerRef.current.scrollToBlock(blockIndex);
    } else {
      // If no transcriptIdx provided, try to scroll the first transcript
      transcriptViewerRef.current?.scrollToBlock(blockIndex);
    }
  }, []);

  return (
    <Suspense fallback={<div>Loading...</div>}>
      <div className="flex-1 flex space-x-3 min-h-0">
        <TranscriptViewer 
          ref={transcriptViewerRef} 
          alt={false} 
          otherTranscriptRef={altTranscriptViewerRef}
        />
        <TranscriptViewer 
          ref={altTranscriptViewerRef} 
          alt={true} 
          otherTranscriptRef={transcriptViewerRef}
        />
        <DiffPanel 
          agentRunIds={[agentRunIds[0], agentRunIds[1]]}
          scrollToBlock={handleDiffScrollToBlock}
        />
      </div>
    </Suspense>
  );
}
