'use client';

import { useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ChatArea,
  SuggestedMessage,
} from '@/app/dashboard/[collection_id]/components/chat/ChatArea';
import { ChatHeader } from '@/app/dashboard/[collection_id]/components/chat/ChatHeader';
import {
  NavigateToCitation,
  TextWithCitations,
} from '@/components/CitationRenderer';
import { JudgeResultWithCitations } from '@/app/store/rubricSlice';
import { useTranscriptChat } from '@/app/hooks/use-transcript-chat';
import { cn } from '@/lib/utils';

export interface TranscriptChatProps {
  runId: string;
  collectionId?: string;

  // Result-specific props
  judgeResult?: JudgeResultWithCitations | null;
  resultContext?: {
    rubricId: string;
    resultId: string;
  };

  // Navigation and citation handling
  onNavigateToCitation?: NavigateToCitation;

  // UI customization
  suggestedMessages?: SuggestedMessage[];
  title?: string;

  // Layout
  className?: string;
}

const defaultSuggestedMessages: SuggestedMessage[] = [
  {
    label: 'Explain mistakes',
    message: 'Explain mistakes the agent made, if there are any.',
  },
  {
    label: 'Identify unusual behavior',
    message:
      'Identify any unusual or unexpected behavior on the part of the agent.',
  },
];

const resultSpecificSuggestedMessages: SuggestedMessage[] = [
  {
    label: "Play devil's advocate",
    message:
      "Play devil's advocate. The judge result claims that the transcript matches the rubric. Is there a reasonable case to be made that the transcript *does not* match the rubric?",
  },
  {
    label: 'Provide context for rubric match',
    message:
      'Summarize the context leading up to the behavior that matched the rubric',
  },
  {
    label: 'Explain judge result in more detail',
    message:
      'Please explain the judge result in more detail. Walk through the rubric step by step and explain why the result matched.',
  },
];

export default function TranscriptChat({
  runId,
  collectionId: propCollectionId,
  judgeResult,
  resultContext,
  onNavigateToCitation,
  title = 'Transcript Chat',
  className = 'flex flex-col h-full space-y-2',
}: TranscriptChatProps) {
  const params = useParams();
  const router = useRouter();

  // Use provided collectionId or extract from params
  const collectionId = propCollectionId || (params.collection_id as string);

  const {
    sessionId,
    messages,
    isLoading,
    sendMessage: onSendMessage,
    resetChat,
  } = useTranscriptChat({ runId, collectionId, judgeResult });

  // Handle citation navigation
  const handleNavigateToCitation: NavigateToCitation = useCallback(
    ({ citation, newTab }) => {
      if (onNavigateToCitation) {
        onNavigateToCitation({ citation, newTab });
      } else if (resultContext) {
        // Default navigation for result context
        router.push(
          `/dashboard/${collectionId}/rubric/${resultContext.rubricId}/result/${resultContext.resultId}`,
          { scroll: false } as any
        );
      }
      // For general transcript chat, we don't have a default navigation
    },
    [onNavigateToCitation, resultContext, router, collectionId]
  );

  // Determine which suggested messages to use
  const finalSuggestedMessages = judgeResult
    ? resultSpecificSuggestedMessages
    : defaultSuggestedMessages;

  // Generate header element if judge result provided
  const judgeResultElement = judgeResult?.value ? (
    <div className="w-full mx-auto max-w-4xl">
      <div className="bg-indigo-bg border border-indigo-border rounded-md p-2 mt-2 text-xs text-primary leading-snug">
        <TextWithCitations
          text={judgeResult.value}
          citations={judgeResult.citations || []}
          onNavigate={handleNavigateToCitation}
        />
      </div>
    </div>
  ) : undefined;

  const headerElement = (
    <ChatHeader
      title={title}
      onReset={resetChat}
      canReset={sessionId !== null && messages.length > 0}
    />
  );

  return (
    <div
      className={cn(
        'flex flex-col min-w-0 h-full w-full mx-auto max-w-4xl',
        className
      )}
    >
      {sessionId ? (
        <ChatArea
          isReadonly={false}
          messages={messages}
          onSendMessage={onSendMessage}
          isLoading={isLoading}
          headerElement={
            <>
              {headerElement}
              {judgeResultElement}
            </>
          }
          hideAssistantAvatar={true}
          suggestedMessages={finalSuggestedMessages}
          onNavigateToCitation={handleNavigateToCitation}
          byoFlexDiv={true}
        />
      ) : (
        headerElement
      )}
    </div>
  );
}
