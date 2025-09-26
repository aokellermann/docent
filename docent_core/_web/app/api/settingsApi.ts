import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { BASE_URL } from '@/app/constants';

export interface FreeUsageModelBreakdown {
  model: string;
  fraction_used: number;
}

interface FreeUsageResponseNoCap {
  has_cap: false;
}

export interface FreeUsageResponseWithCap {
  has_cap: true;
  window_seconds: number;
  fraction_used: number | null;
  models: FreeUsageModelBreakdown[];
  note: string;
}
export type FreeUsageResponse =
  | FreeUsageResponseWithCap
  | FreeUsageResponseNoCap;

export interface ByokModelBreakdown {
  model: string;
  total_cents: number;
}

export interface ByokKeyUsage {
  api_key_id: string;
  total_cents: number;
  models: ByokModelBreakdown[];
}

export interface ByokUsageResponse {
  window_seconds: number | null;
  keys: ByokKeyUsage[];
}

export interface UsageSummaryResponse {
  window_seconds: number;
  free: FreeUsageResponse;
  byok: ByokUsageResponse;
}

export interface ModelApiKey {
  id: string;
  provider: string;
  masked_api_key: string;
}

export const settingsApi = createApi({
  reducerPath: 'settingsApi',
  baseQuery: fetchBaseQuery({
    baseUrl: `${BASE_URL}/rest/settings`,
    credentials: 'include',
  }),
  endpoints: (build) => ({
    getUsageSummary: build.query<UsageSummaryResponse, void>({
      query: () => `/usage/summary`,
    }),
    getModelApiKeys: build.query<ModelApiKey[], void>({
      query: () => `/model-api-keys`,
    }),
    upsertModelApiKey: build.mutation<
      ModelApiKey,
      { provider: string; api_key: string }
    >({
      query: (body) => ({
        url: `/model-api-keys`,
        method: 'PUT',
        body,
      }),
    }),
    deleteModelApiKey: build.mutation<
      { message: string },
      { provider: string }
    >({
      query: ({ provider }) => ({
        url: `/model-api-keys/${provider}`,
        method: 'DELETE',
      }),
    }),
  }),
});

export const {
  useGetUsageSummaryQuery,
  useGetModelApiKeysQuery,
  useUpsertModelApiKeyMutation,
  useDeleteModelApiKeyMutation,
} = settingsApi;
