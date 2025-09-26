import { skipToken } from '@reduxjs/toolkit/query';
import { useParams, useRouter } from 'next/navigation';
import { useEffect } from 'react';

import {
  useGetResultByAgentRunQuery,
  useGetResultByIdQuery,
} from '@/app/api/rubricApi';
import { useGetAgentRunQuery } from '@/app/api/collectionApi';

interface UseRouteGuardProps {
  version: number | null;
}

export const useRouteGuard = ({ version }: UseRouteGuardProps) => {
  const {
    collection_id: collectionId,
    rubric_id: rubricId,
    agent_run_id: agentRunId,
    result_id: resultId,
  } = useParams<{
    collection_id: string;
    rubric_id: string;
    agent_run_id?: string;
    result_id?: string;
  }>();

  const router = useRouter();

  // This file guards the following routes:
  // 1. rubric/[rubric_id]/agent_run/[agent_run_id]
  // 2. rubric/[rubric_id]/agent_run/[agent_run_id]/result/[result_id]
  // 3. rubric/[rubric_id]/result/[result_id] (legacy route)

  //--------------------------------

  const {
    data: result,
    isLoading: isLoadingResultByAgentRun,
    isError: isErrorResultByAgentRun,
  } = useGetResultByAgentRunQuery(
    agentRunId && version
      ? {
          collectionId,
          rubricId,
          agentRunId,
          version,
        }
      : skipToken
  );

  // Guard for (1)
  // > We have an agent_run_id so we get the first result for that run + rubric and redirect

  useEffect(() => {
    // If we're already on a result page (2) or (3), don't redirect
    if (isLoadingResultByAgentRun || resultId) return;

    // If found, redirect to the result page
    if (result && !isErrorResultByAgentRun) {
      router.push(
        `/dashboard/${collectionId}/rubric/${rubricId}/agent_run/${agentRunId}/result/${result?.id}`
      );
    }
  }, [
    isLoadingResultByAgentRun,
    isErrorResultByAgentRun,
    result,
    agentRunId,
    collectionId,
    rubricId,
    router,
    resultId,
  ]);

  // Guard for (1) and (2)
  // A general check for whether the agent run on the route exists.
  // If it doesn't, return to the rubric page.

  const { data: agentRun, isLoading: isLoadingAgentRun } = useGetAgentRunQuery(
    agentRunId
      ? {
          collectionId,
          agentRunId,
        }
      : skipToken
  );

  useEffect(() => {
    if (isLoadingAgentRun) return;

    if (!agentRun) {
      router.push(`/dashboard/${collectionId}/rubric/${rubricId}`);
    }
  }, [isLoadingAgentRun, agentRun, collectionId, rubricId, router]);

  // Guard for (3)
  // This is a legacy route, so we just get the result and either
  // redirect to the new result page or the rubric page.

  const { data: judgeResult, isLoading: isLoadingResultById } =
    useGetResultByIdQuery(
      resultId
        ? {
            collectionId,
            resultId,
          }
        : skipToken
    );

  useEffect(() => {
    // Don't run this effect if we're on a new route
    if (isLoadingResultById || agentRunId) return;

    // If not found, redirect to the rubric page
    // else, redirect to the result page
    if (!judgeResult) {
      router.push(`/dashboard/${collectionId}/rubric/${rubricId}`);
    } else {
      router.push(
        `/dashboard/${collectionId}/rubric/${rubricId}/agent_run/${judgeResult.agent_run_id}/result/${judgeResult?.id}`
      );
    }
  }, [
    isLoadingResultById,
    judgeResult,
    collectionId,
    rubricId,
    router,
    agentRunId,
  ]);
};
