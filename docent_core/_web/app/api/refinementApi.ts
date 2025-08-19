import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { BASE_URL } from '@/app/constants';
import sseService from '../services/sseService';
import { ChatMessage } from '@/app/types/transcriptTypes';
import { setMessages } from '@/app/store/refinementSlice';
import { Rubric } from '@/app/store/rubricSlice';

export interface RefinementAgentSession {
  id: string;
  rubric_id: string;
  messages: ChatMessage[];
}

export const refinementApi = createApi({
  reducerPath: 'refinementApi',
  baseQuery: fetchBaseQuery({
    baseUrl: `${BASE_URL}/rest/refinement`,
    credentials: 'include',
  }),
  tagTypes: ['RefinementSession'],
  endpoints: (build) => ({
    getCurrentState: build.query<
      RefinementAgentSession,
      { collectionId: string; sessionId: string }
    >({
      query: ({ collectionId, sessionId }) =>
        `/${collectionId}/refinement-session/${sessionId}/state`,
      providesTags: (result) =>
        result ? [{ type: 'RefinementSession' as const, id: result.id }] : [],
    }),

    createOrGetSession: build.mutation<
      { id: string },
      { collectionId: string; rubricId: string }
    >({
      query: ({ collectionId, rubricId }) => ({
        url: `/${collectionId}/refinement-session/create/${rubricId}`,
        method: 'POST',
      }),
      invalidatesTags: (result) =>
        result ? [{ type: 'RefinementSession' as const, id: result.id }] : [],
    }),

    startRefinementSession: build.mutation<
      { session_id: string; job_id: string | null; rubric_id: string },
      { collectionId: string; sessionId: string }
    >({
      query: ({ collectionId, sessionId }) => ({
        url: `/${collectionId}/refinement-session/start/${sessionId}`,
        method: 'POST',
      }),
      invalidatesTags: (result) =>
        result
          ? [{ type: 'RefinementSession' as const, id: result.session_id }]
          : [],
    }),

    listenToRefinementJob: build.query<
      { isSSEConnected: boolean },
      { collectionId: string; jobId: string }
    >({
      queryFn: () => ({ data: { isSSEConnected: true } }),
      keepUnusedDataFor: 0,
      async onCacheEntryAdded(
        { collectionId, jobId },
        { dispatch, updateCachedData, cacheEntryRemoved }
      ) {
        const url = `/rest/refinement/${collectionId}/refinement-job/${jobId}/listen`;

        const { onCancel } = sseService.createEventSource(
          url,
          (data: RefinementAgentSession) => {
            dispatch(setMessages(data.messages));
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
      providesTags: ['RefinementSession'],
    }),

    postMessageToRefinementSession: build.mutation<
      { job_id: string; rsession: RefinementAgentSession },
      { collectionId: string; sessionId: string; message: string }
    >({
      query: ({ collectionId, sessionId, message }) => ({
        url: `/${collectionId}/refinement-session/${sessionId}/message`,
        method: 'POST',
        body: { message },
      }),
      invalidatesTags: (result, error, arg) => [
        { type: 'RefinementSession' as const, id: arg.sessionId },
      ],
    }),

    postRubricUpdateToRefinementSession: build.mutation<
      { job_id: string; rsession: RefinementAgentSession },
      { collectionId: string; sessionId: string; rubric: Rubric }
    >({
      query: ({ collectionId, sessionId, rubric }) => ({
        url: `/${collectionId}/refinement-session/${sessionId}/rubric-update`,
        method: 'POST',
        body: rubric,
      }),
      invalidatesTags: (result, error, arg) => [
        { type: 'RefinementSession' as const, id: arg.sessionId },
      ],
    }),
  }),
});

export const {
  useGetCurrentStateQuery,
  useLazyGetCurrentStateQuery,
  useCreateOrGetSessionMutation,
  useStartRefinementSessionMutation,
  usePostMessageToRefinementSessionMutation,
  usePostRubricUpdateToRefinementSessionMutation,
  useListenToRefinementJobQuery,
  useLazyListenToRefinementJobQuery,
} = refinementApi;
