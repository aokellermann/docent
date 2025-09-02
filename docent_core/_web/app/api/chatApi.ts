import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { BASE_URL } from '@/app/constants';
import sseService from '../services/sseService';
import { ChatMessage } from '@/app/types/transcriptTypes';

export interface ChatSession {
  id: string;
  run_ids: string[];
  rubric_id: string | null;
  messages: ChatMessage[];
}

export const chatApi = createApi({
  reducerPath: 'chatApi',
  baseQuery: fetchBaseQuery({
    baseUrl: `${BASE_URL}/rest/chat`,
    credentials: 'include',
  }),
  tagTypes: ['ChatSession'],
  endpoints: (build) => ({
    getChatState: build.query<
      { messages: ChatMessage[]; session_id: string },
      { collectionId: string; runId: string; sessionId: string }
    >({
      query: ({ collectionId, runId, sessionId }) => ({
        url: `/${collectionId}/${runId}/session/${sessionId}/state`,
        method: 'GET',
      }),
      providesTags: (result) =>
        result ? [{ type: 'ChatSession' as const, id: result.session_id }] : [],
    }),

    getOrCreateChatSession: build.mutation<
      { session_id: string },
      {
        collectionId: string;
        runId: string;
        resultId: string | null;
        forceCreate?: boolean;
      }
    >({
      query: ({ collectionId, runId, resultId, forceCreate }) => {
        const baseUrl = resultId
          ? `/${collectionId}/${runId}/session/get?result_id=${resultId}`
          : `/${collectionId}/${runId}/session/get`;
        const url = forceCreate
          ? `${baseUrl}${resultId ? '&' : '?'}force_create=true`
          : baseUrl;

        return {
          url,
          method: 'POST',
        };
      },
      invalidatesTags: (result) =>
        result ? [{ type: 'ChatSession' as const, id: result.session_id }] : [],
    }),

    listenToChatJob: build.query<
      { isSSEConnected: boolean; messages: ChatMessage[] },
      { collectionId: string; runId: string; jobId: string }
    >({
      queryFn: () => ({ data: { isSSEConnected: true, messages: [] } }),
      keepUnusedDataFor: 30, // Keep cache for 30 seconds to allow state updates
      async onCacheEntryAdded(
        { collectionId, runId, jobId },
        { dispatch, updateCachedData, cacheEntryRemoved }
      ) {
        const url = `/rest/chat/${collectionId}/${runId}/job/${jobId}/listen`;

        const { onCancel } = sseService.createEventSource(
          url,
          (data: { messages: ChatMessage[]; session_id: string }) => {
            updateCachedData((draft) => {
              draft.messages = data.messages;
            });
          },
          () => {
            updateCachedData((draft) => {
              draft.isSSEConnected = false;
            });
          },
          dispatch
        );

        await cacheEntryRemoved;
        onCancel();
      },
    }),

    postChatMessage: build.mutation<
      { job_id: string; messages: ChatMessage[] },
      {
        collectionId: string;
        runId: string;
        sessionId: string;
        message: string;
      }
    >({
      query: ({ collectionId, runId, sessionId, message }) => ({
        url: `/${collectionId}/${runId}/session/${sessionId}/message`,
        method: 'POST',
        body: { message },
      }),
      invalidatesTags: (result, error, arg) => [
        { type: 'ChatSession' as const, id: arg.sessionId },
      ],
    }),
  }),
});

export const {
  useGetChatStateQuery,
  useLazyGetChatStateQuery,
  useGetOrCreateChatSessionMutation,
  usePostChatMessageMutation,
  useListenToChatJobQuery,
  useLazyListenToChatJobQuery,
} = chatApi;
