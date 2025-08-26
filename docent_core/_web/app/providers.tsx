'use client';
import posthog from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';
import { Provider } from 'react-redux';

import store from './store/store';

if (typeof window !== 'undefined') {
  if (
    process.env.NEXT_PUBLIC_POSTHOG_API_KEY &&
    process.env.NEXT_PUBLIC_POSTHOG_API_HOST
  ) {
    posthog.init(process.env.NEXT_PUBLIC_POSTHOG_API_KEY, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_API_HOST,
      disable_session_recording: true,
      autocapture: true,
      capture_heatmaps: true,
    });
    console.log(
      'PostHog initialized, logging to',
      process.env.NEXT_PUBLIC_POSTHOG_API_HOST
    );
  }
}
export function CSPostHogProvider({ children }: { children: React.ReactNode }) {
  return <PostHogProvider client={posthog}>{children}</PostHogProvider>;
}

export function ReduxProvider({ children }: { children: React.ReactNode }) {
  return <Provider store={store}>{children}</Provider>;
}
