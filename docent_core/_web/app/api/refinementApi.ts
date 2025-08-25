import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { BASE_URL } from '@/app/constants';
import sseService from '../services/sseService';
import { RefinementAgentSession } from '@/app/store/refinementSlice';
import { Rubric } from '@/app/store/rubricSlice';

export const refinementApi = createApi({
  reducerPath: 'refinementApi',
  baseQuery: fetchBaseQuery({
    baseUrl: `${BASE_URL}/rest/refinement`,
    credentials: 'include',
  }),
  tagTypes: ['RefinementSession'],
  endpoints: (build) => ({
    createOrGetRefinementSession: build.mutation<
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
      { isSSEConnected: boolean; rsession: RefinementAgentSession | null },
      { collectionId: string; jobId: string }
    >({
      queryFn: () => ({
        data: {
          isSSEConnected: true,
          rsession: null,
        },
      }),
      keepUnusedDataFor: 0,
      async onCacheEntryAdded(
        { collectionId, jobId },
        { dispatch, updateCachedData, cacheEntryRemoved }
      ) {
        const url = `/rest/refinement/${collectionId}/refinement-job/${jobId}/listen`;

        const { onCancel } = sseService.createEventSource(
          url,
          (data: RefinementAgentSession) => {
            updateCachedData((draft) => {
              draft.rsession = data;
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
  useCreateOrGetRefinementSessionMutation,
  useStartRefinementSessionMutation,
  usePostMessageToRefinementSessionMutation,
  usePostRubricUpdateToRefinementSessionMutation,
  useListenToRefinementJobQuery,
  useLazyListenToRefinementJobQuery,
} = refinementApi;
