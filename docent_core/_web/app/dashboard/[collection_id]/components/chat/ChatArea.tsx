'use client';

import { useScrollToBottom } from '@/app/hooks/use-scroll-to-bottom';
import { motion } from 'framer-motion';

import { cn } from '@/lib/utils';
import { SparklesIcon } from 'lucide-react';
import { useEffect } from 'react';
import Markdown from './Markdown';
import InputArea from './InputArea';
import {
  ChatMessage,
  Content as ChatContent,
} from '@/app/types/transcriptTypes';

interface ChatAreaProps {
  isReadonly: boolean;
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  isLoading?: boolean;
  byoFlexDiv: boolean;
  __showThinkingSpacerAfterFirstMessage?: boolean;
}

/**
 * TODO(mengk): fix the thinking spacer logic, very hacky right now
 */
export default function ChatArea({
  isReadonly,
  messages,
  onSendMessage,
  isLoading = false,
  byoFlexDiv = false,
  __showThinkingSpacerAfterFirstMessage = false,
}: ChatAreaProps) {
  const {
    containerRef,
    endRef,
    onViewportEnter,
    onViewportLeave,
    scrollToBottom,
  } = useScrollToBottom();

  const lastMessage = messages[messages.length - 1];
  const showThinkingSpacer =
    (isLoading &&
      lastMessage?.role !== 'assistant' &&
      lastMessage?.role !== 'tool') ||
    (messages.length === 1 && __showThinkingSpacerAfterFirstMessage);

  useEffect(() => {
    if (lastMessage?.role === 'user' && isLoading) {
      scrollToBottom();
    }
  }, [scrollToBottom, lastMessage?.role, isLoading]);

  const coreComponent = (
    <>
      <div
        className="flex-1 flex flex-col min-w-0 gap-6 overflow-y-scroll relative custom-scrollbar pt-3"
        // Explaining the pt-3: The card has padding 3, and the gap is 6, so 6-3=3
        ref={containerRef}
      >
        {messages.map((message, index) => (
          <Message
            key={index}
            message={message}
            isLoadingPlaceholder={false}
            isReadonly={isReadonly}
            requiresScrollPadding={
              !showThinkingSpacer &&
              index === messages.length - 1 &&
              message.role === 'assistant'
            }
          />
        ))}
        {showThinkingSpacer && (
          <Message
            message={{
              role: 'assistant',
              content: 'Thinking...',
            }}
            isLoadingPlaceholder={true}
            isReadonly={isReadonly}
            requiresScrollPadding={true}
          />
        )}

        {/* Sentinel to detect when viewport is at the bottom and to provide a scroll target */}
        <motion.div
          ref={endRef}
          onViewportEnter={onViewportEnter}
          onViewportLeave={onViewportLeave}
          className="min-h-1"
          data-testid="messages-end"
        />
      </div>

      <form className="flex mx-auto px-4 bg-background gap-2 w-full md:max-w-3xl">
        <InputArea
          onSendMessage={onSendMessage}
          disabled={isLoading || isReadonly}
          isLoading={isLoading}
        />
      </form>
    </>
  );

  if (byoFlexDiv) {
    return coreComponent;
  } else {
    return (
      <div className="flex-1 flex flex-col min-w-0 bg-background">
        {coreComponent}
      </div>
    );
  }
}

interface MessageProps {
  message: ChatMessage;
  isLoadingPlaceholder: boolean;
  isReadonly: boolean;
  requiresScrollPadding: boolean;
}

function Message({
  message,
  isLoadingPlaceholder,
  isReadonly,
  requiresScrollPadding,
}: MessageProps) {
  // Render tool messages in the same style as tool calls
  const renderToolMessage = () => {
    if (message.role !== 'tool') return null;
    const contentList = Array.isArray(message.content)
      ? message.content
      : ([{ type: 'text', text: message.content }] as ChatContent[]);
    const contentText = contentList
      .map((part) => {
        if (part.type === 'text') return part.text ?? '';
        if (part.type === 'reasoning') return part.reasoning ?? '';
        return '';
      })
      .filter((t) => (t || '').trim() !== '')
      .join('\n\n');

    return (
      <div className="mt-1 p-1.5 bg-secondary/85 rounded text-xs break-all whitespace-pre-wrap">
        <div className="text-[10px] text-muted-foreground mb-0.5">
          {message.tool_call_id ? (
            <>Tool Call ID: {message.tool_call_id}</>
          ) : (
            <>Tool Message</>
          )}
        </div>
        <div className="font-mono">
          {message.function && (
            <span className="font-semibold">{message.function}</span>
          )}
          {message.error && (
            <div className="mt-1 text-red-text">
              Error: {message.error.message}
            </div>
          )}
        </div>
        {contentText && (
          <div className="mt-1 font-mono whitespace-pre-wrap break-all">
            {contentText}
          </div>
        )}
      </div>
    );
  };

  // Render tool calls attached to assistant messages
  const renderToolCalls = () => {
    if (
      message.role === 'assistant' &&
      'tool_calls' in message &&
      message.tool_calls
    ) {
      return message.tool_calls.map((tool, i) => (
        <div
          key={i}
          className="mt-1 p-1.5 bg-secondary/85 rounded text-xs break-all whitespace-pre-wrap"
        >
          <div className="text-[10px] text-muted-foreground mb-0.5">
            Tool Call ID: {tool.id}
          </div>
          {tool.view ? (
            <span className="font-mono">{tool.view.content}</span>
          ) : (
            <div className="font-mono">
              <span className="font-semibold">{tool.function}</span>
              <span className="text-muted-foreground">
                (
                {Object.entries(tool.arguments || {})
                  .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                  .join(', ')}
                )
              </span>
            </div>
          )}
        </div>
      ));
    }
    return null;
  };

  const renderBubble = (key: string | number, children: React.ReactNode) => (
    <div key={key} className="flex flex-row gap-2 items-start">
      {/* {message.role === 'user' && !isReadonly && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              data-testid="message-edit-button"
              variant="ghost"
              className="px-2 h-fit rounded-full text-muted-foreground opacity-0 group-hover/message:opacity-100"
              onClick={() => {
                setMode('edit');
              }}
            >
              <PencilIcon />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Edit message</TooltipContent>
        </Tooltip>
      )} */}

      <div
        data-testid="message-content"
        className={cn('flex flex-col gap-4', {
          'bg-primary text-primary-foreground px-3 py-2 rounded-xl':
            message.role === 'user',
        })}
      >
        {children}
      </div>
    </div>
  );

  return (
    <div
      //   data-testid={`message-${message.role}`}
      className="w-full mx-auto max-w-4xl px-4 group/message text-sm"
      //   initial={{ y: 5, opacity: 0 }}
      //   animate={{ y: 0, opacity: 1 }}
      data-role={message.role}
    >
      <div
        className={cn(
          'flex gap-4 w-full group-data-[role=user]/message:ml-auto group-data-[role=user]/message:max-w-2xl group-data-[role=user]/message:w-fit'
        )}
      >
        {(message.role === 'assistant' || message.role === 'tool') && (
          <div className="size-8 flex items-center rounded-full justify-center ring-1 shrink-0 ring-border bg-background">
            <div className="translate-y-px">
              <SparklesIcon size={14} />
            </div>
          </div>
        )}

        <div
          className={cn('flex flex-col gap-4 w-full', {
            'min-h-64': message.role === 'assistant' && requiresScrollPadding,
          })}
        >
          {(() => {
            // For tool messages, render the styled panel inside a standard bubble
            if (message.role === 'tool') {
              return renderBubble('tool-message', renderToolMessage());
            }

            const contentList = Array.isArray(message.content)
              ? message.content
              : [{ type: 'text', text: message.content } as ChatContent];

            const parts = contentList.map((part, index) => {
              const key = `message-part-${index}`;
              if (part.type === 'reasoning') {
                const text = part.reasoning ?? '';
                if (!text.trim()) return null;
                return renderBubble(
                  key,
                  <div className="text-muted-foreground">{text}</div>
                );
              }
              if (part.type === 'text') {
                const text = part.text ?? '';
                if (!text.trim()) return null;
                if (isLoadingPlaceholder) {
                  return renderBubble(
                    key,
                    <div className="animate-pulse text-muted-foreground">
                      {text}
                    </div>
                  );
                }
                return renderBubble(key, <Markdown>{text}</Markdown>);
              }
              // ignore images and unknown types for now
              return null;
            });
            return parts;
          })()}
          {renderToolCalls()}
        </div>
      </div>
    </div>
  );
}
