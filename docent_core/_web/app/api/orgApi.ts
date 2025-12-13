import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';
import { BASE_URL } from '@/app/constants';

export type OrganizationRole = 'member' | 'admin';

export interface OrganizationWithRole {
  id: string;
  name: string;
  description: string | null;
  my_role: OrganizationRole;
}

export interface OrganizationMember {
  organization_id: string;
  user: {
    id: string;
    email: string;
    organization_ids: string[];
    is_anonymous: boolean;
  };
  role: OrganizationRole;
}

export const orgApi = createApi({
  reducerPath: 'orgApi',
  baseQuery: fetchBaseQuery({
    baseUrl: `${BASE_URL}/rest`,
    credentials: 'include',
  }),
  tagTypes: ['Organizations', 'OrgMembers'],
  endpoints: (build) => ({
    getMyOrganizations: build.query<OrganizationWithRole[], void>({
      query: () => `/organizations`,
      providesTags: ['Organizations'],
    }),
    createOrganization: build.mutation<
      OrganizationWithRole,
      { name: string; description?: string }
    >({
      query: (body) => ({
        url: `/organizations`,
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Organizations'],
    }),
    getOrganizationMembers: build.query<OrganizationMember[], string>({
      query: (orgId) => `/organizations/${orgId}/members`,
      providesTags: (_result, _err, orgId) => [
        { type: 'OrgMembers', id: orgId },
      ],
    }),
    addOrganizationMember: build.mutation<
      OrganizationMember[],
      { orgId: string; email: string; role: OrganizationRole }
    >({
      query: ({ orgId, email, role }) => ({
        url: `/organizations/${orgId}/members`,
        method: 'POST',
        body: { email, role },
      }),
      invalidatesTags: (_result, _err, { orgId }) => [
        { type: 'OrgMembers', id: orgId },
      ],
    }),
    updateOrganizationMemberRole: build.mutation<
      OrganizationMember[],
      { orgId: string; memberUserId: string; role: OrganizationRole }
    >({
      query: ({ orgId, memberUserId, role }) => ({
        url: `/organizations/${orgId}/members/${memberUserId}`,
        method: 'PATCH',
        body: { role },
      }),
      invalidatesTags: (_result, _err, { orgId }) => [
        { type: 'OrgMembers', id: orgId },
      ],
    }),
    removeOrganizationMember: build.mutation<
      OrganizationMember[],
      { orgId: string; memberUserId: string }
    >({
      query: ({ orgId, memberUserId }) => ({
        url: `/organizations/${orgId}/members/${memberUserId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _err, { orgId }) => [
        { type: 'OrgMembers', id: orgId },
      ],
    }),
  }),
});

export const {
  useGetMyOrganizationsQuery,
  useCreateOrganizationMutation,
  useGetOrganizationMembersQuery,
  useAddOrganizationMemberMutation,
  useUpdateOrganizationMemberRoleMutation,
  useRemoveOrganizationMemberMutation,
} = orgApi;
