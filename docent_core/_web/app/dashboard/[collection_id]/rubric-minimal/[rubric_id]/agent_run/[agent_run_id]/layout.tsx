'use client';

import React, { Suspense, useEffect, useRef } from 'react';
import { PanelLeft } from 'lucide-react';
import AgentRunViewer, {
  AgentRunViewerHandle,
} from '../../../../agent_run/components/AgentRunViewer';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useGetRubricRunStateQuery } from '@/app/api/rubricApi';

import { useAppDispatch } from '@/app/store/hooks';
import {
  setRunCitations,
  toggleJudgeLeftSidebar,
} from '@/app/store/transcriptSlice';
import { Button } from '@/components/ui/button';
import {
  useCitationNavigation,
  wrapCitationHandlerWithRouting,
} from '@/providers/CitationNavigationProvider';
import { useRubricVersion } from '@/providers/use-rubric-version';

export default function MinimalJudgeResultPage() {
  const {
    agent_run_id: agentRunId,
    collection_id: collectionId,
    rubric_id: rubricId,
    result_id: resultId,
  } = useParams<{
    agent_run_id: string;
    collection_id: string;
    rubric_id: string;
    result_id?: string;
  }>();

  const dispatch = useAppDispatch();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCommentId = searchParams.get('comment_id');
  const citationNav = useCitationNavigation();
  const { version } = useRubricVersion();
  const isResultRoute = !!resultId;

  const { data: rubricRunState } = useGetRubricRunStateQuery(
    {
      collectionId,
      rubricId,
      version: version ?? null,
      labelSetId: null,
    },
    { skip: !isResultRoute }
  );

  const currentAgentRunGroup = rubricRunState?.results?.find((arr) =>
    arr.results.some((r) => r.id === resultId)
  );
  const result = currentAgentRunGroup?.results.find((r) => r.id === resultId);
  const citations = result?.output?.explanation?.citations;

  const agentRunViewerRef = useRef<AgentRunViewerHandle>(null);
  const alreadyScrolledRef = useRef(false);

  useEffect(() => {
    if (agentRunId && result) {
      dispatch(
        setRunCitations({
          [agentRunId]: citations || [],
        })
      );
    }
  }, [result, agentRunId, citations, dispatch]);

  useEffect(() => {
    alreadyScrolledRef.current = false;
  }, [agentRunId, resultId]);

  useEffect(() => {
    if (alreadyScrolledRef.current) return;
    if (initialCommentId) return;
    if (!agentRunId || !result) return;

    const citation = citations && citations.length > 0 ? citations[0] : null;
    if (!citation) return;

    agentRunViewerRef.current?.focusCitationTarget(citation.target);
    alreadyScrolledRef.current = true;
  }, [agentRunId, result, citations, initialCommentId]);

  useEffect(() => {
    if (!agentRunId || !collectionId) return;

    if (citationNav?.registerHandler) {
      const baseHandler = ({ target }: { target: any }) => {
        agentRunViewerRef.current?.focusCitationTarget(target);
      };

      const wrappedHandler = wrapCitationHandlerWithRouting(
        baseHandler,
        router,
        {
          collectionId,
          currentAgentRunId: agentRunId,
          rubricId,
          rubricRouteBase: 'rubric-minimal',
        },
        citationNav.setPendingCitation
      );

      citationNav.registerHandler(wrappedHandler);
    }
    return () => {
      if (citationNav?.registerHandler) {
        citationNav.registerHandler(null);
      }
    };
  }, [citationNav, agentRunId, collectionId, rubricId, router]);

  return (
    <Suspense>
      <div className="h-full overflow-hidden flex flex-col space-y-2">
        <AgentRunViewer
          ref={agentRunViewerRef}
          agentRunId={agentRunId}
          defaultSidebarVisible={false}
          headerLeftActions={
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 cursor-default"
              onClick={() => dispatch(toggleJudgeLeftSidebar())}
            >
              <PanelLeft className="h-4 w-4" />
            </Button>
          }
        />
      </div>
    </Suspense>
  );
}
