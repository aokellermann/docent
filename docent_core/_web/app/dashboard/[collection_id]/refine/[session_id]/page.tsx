'use client';

import { Card } from '@/components/ui/card';
import ChatArea from '../../components/chat/ChatArea';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { skipToken } from '@reduxjs/toolkit/query';
import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import {
  useStartRefinementSessionMutation,
  usePostMessageToRefinementSessionMutation,
  useListenToRefinementJobQuery,
  usePostRubricUpdateToRefinementSessionMutation,
} from '@/app/api/refinementApi';
import RubricEditor from '../../components/RubricEditor';
import { Rubric } from '@/app/store/rubricSlice';
import { setMessages } from '@/app/store/refinementSlice';

export default function RefinePage() {
  const params = useParams();
  const dispatch = useAppDispatch();
  const collectionId = (params as any)?.collection_id as string | undefined;
  const sessionId = (params as any)?.session_id as string | undefined;

  const messages = useAppSelector((s) => s.refinement.messages);
  const [jobId, setJobId] = useState<string | null>(null);
  const [rubricId, setRubricId] = useState<string | null>(null);

  // Start the refinement session on page load
  const [startRefinementSession] = useStartRefinementSessionMutation();
  // useEffect is safe because the endpoint is idempotent
  useEffect(() => {
    if (!collectionId || !sessionId) return;
    startRefinementSession({ collectionId, sessionId })
      .unwrap()
      .then((res) => {
        if (res?.job_id) setJobId(res.job_id);
        if (res?.rubric_id) setRubricId(res.rubric_id);
      })
      .catch(() => {});
  }, [collectionId, sessionId, startRefinementSession]);

  // Handle sending messages to the refinement session
  const [postMessage] = usePostMessageToRefinementSessionMutation();
  const [postRubricUpdate] = usePostRubricUpdateToRefinementSessionMutation();
  const onSendMessage = useCallback(
    (message: string) => {
      if (!collectionId || !sessionId) return;
      postMessage({ collectionId, sessionId, message })
        .unwrap()
        .then((res) => {
          if (res?.job_id) setJobId(res.job_id);
        })
        .catch(() => {});
    },
    [collectionId, sessionId, postMessage]
  );

  // Start listening to the job state via SSE when we have a jobId
  const { data: { isSSEConnected } = { isSSEConnected: false } } =
    useListenToRefinementJobQuery(
      jobId && collectionId ? { collectionId, jobId } : skipToken
    );

  // Post-process the messages a little bit, determine when to increment rubric version
  const [showDiff, setShowDiff] = useState<boolean>(false);
  const [refinementRubricVersion, setRefinementRubricVersion] = useState<
    number | null
  >(null);

  const processedMessages = useMemo(() => {
    const ans = messages.filter((message) => {
      if (
        message.role === 'tool' &&
        message.function === 'set_rubric' &&
        !message.error
      ) {
        // We know the content must be the version of the rubric
        // We don't want to render it and instead use it for something else
        return false;
      } else {
        return true;
      }
    });
    return ans;
  }, [messages]);

  // Move state updates out of useMemo and into an effect
  useEffect(() => {
    let maxVersion: number | null = null;
    for (const message of messages) {
      if (
        message.role === 'tool' &&
        message.function === 'set_rubric' &&
        !message.error
      ) {
        const version = Number(message.content);
        maxVersion = Math.max(version, maxVersion ?? 0);
      }
    }

    if (maxVersion === null) return;
    // Only update when the version actually increases or changes
    if (
      refinementRubricVersion !== maxVersion &&
      !(
        refinementRubricVersion !== null && maxVersion < refinementRubricVersion
      )
    ) {
      setRefinementRubricVersion(maxVersion);
      setShowDiff(true);
    }
  }, [messages, refinementRubricVersion]);

  const [hasChanges, setHasChanges] = useState<boolean>(false);

  const handleRubricSave = (rubric: Rubric) => {
    if (!collectionId || !sessionId) return;
    if (isSSEConnected) {
      throw new Error('Cannot save rubric while SSE is connected');
    }

    postRubricUpdate({ collectionId, sessionId, rubric })
      .unwrap()
      .then((res) => {
        if (res?.job_id) setJobId(res.job_id);
        if (res?.rsession) {
          dispatch(setMessages(res.rsession.messages));
        }
        setRefinementRubricVersion(rubric.version);
      })
      .catch(() => {});
  };

  return (
    <Card className="flex-1 flex h-full min-h-0 space-x-3 space-y-0">
      <ChatArea
        isReadonly={hasChanges}
        messages={processedMessages}
        onSendMessage={onSendMessage}
        isLoading={isSSEConnected}
      />
      <div className="flex-1 flex flex-col custom-scrollbar overflow-y-scroll">
        {rubricId && (
          <RubricEditor
            rubricId={rubricId}
            rubricVersion={refinementRubricVersion}
            setRubricVersion={setRefinementRubricVersion}
            showDiff={showDiff}
            setShowDiff={setShowDiff}
            editable={!isSSEConnected} // Cannot edit if SSE is connected
            onSave={handleRubricSave}
            onCloseWithoutSave={() => {}}
            onHasUnsavedChangesUpdated={setHasChanges}
          />
        )}
      </div>
    </Card>
  );
}
