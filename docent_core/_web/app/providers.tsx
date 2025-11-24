'use client';
import { useEffect, useRef } from 'react';
import posthogClient from 'posthog-js';
import { PostHogProvider } from 'posthog-js/react';
import { Provider } from 'react-redux';
import { useLocalStorage } from 'usehooks-ts';
import store from './store/store';
import { ReplayPreference } from './types/userTypes';
import { SESSION_REPLAY_PREFERENCE_KEY } from './constants';
import { useUserContext } from './contexts/UserContext';

const maskInputFn = (text: string, element?: HTMLElement | null) => {
  // Do not mask rubric input areas
  // CodeMirror and Monaco components are not masked by default, ignore those
  if (element?.id === 'rubric-input') {
    return text;
  }
  // Otherwise, mask it with asterisks
  return '*'.repeat(text.length);
};

export function CSPostHogProvider({ children }: { children: React.ReactNode }) {
  const initialized = useRef<boolean>(false);
  const { user } = useUserContext();

  useEffect(() => {
    // Only initialize the Posthog client once
    if (initialized.current || !user) return;

    const resolvedReplayKey = SESSION_REPLAY_PREFERENCE_KEY + '_' + user.id;

    // 1. Get the replay preference from localStorage
    // If the value does not exist, set to 'not-set'
    const storedPreference = localStorage.getItem(resolvedReplayKey);
    let initialReplayPreference: ReplayPreference;
    if (storedPreference) {
      try {
        initialReplayPreference = JSON.parse(
          storedPreference
        ) as ReplayPreference;
      } catch {
        // Default to opted out if local storage is corrupted. This should never happen.
        initialReplayPreference = 'opted-out';
      }
    } else {
      localStorage.setItem(resolvedReplayKey, JSON.stringify('not-set'));
      initialReplayPreference = 'not-set';
    }

    // 2. Initialize the Posthog client if the API key and host are set
    if (
      process.env.NEXT_PUBLIC_POSTHOG_API_KEY &&
      process.env.NEXT_PUBLIC_POSTHOG_API_HOST
    ) {
      // Do not record sessions if local storage hydrating, not set, or opted-out
      const disableRecording = ['opted-out', 'not-set', 'loading'].includes(
        initialReplayPreference
      );

      // If the user does not fully opt-in, mask agent runs, metadata, and the agent run table
      const maskTextSelector =
        initialReplayPreference !== 'full-opt-in'
          ? '.agent-run-viewer, .metadata, .agent-run-table'
          : '';

      posthogClient.init(process.env.NEXT_PUBLIC_POSTHOG_API_KEY, {
        api_host: process.env.NEXT_PUBLIC_POSTHOG_API_HOST,
        autocapture: true,
        capture_heatmaps: true,

        // Session recording configuration
        disable_session_recording: disableRecording,
        session_recording: {
          maskAllInputs: true,
          maskInputFn,
          maskTextSelector: maskTextSelector,
        },
      });

      console.log(
        'PostHog initialized, logging to',
        process.env.NEXT_PUBLIC_POSTHOG_API_HOST
      );

      initialized.current = true;
    } else {
      console.log('Posthog not configured.');
      initialized.current = true;
    }
  }, [user]);

  // Watch for changes in replay preference to update config dynamically
  const [replayPreference] = useLocalStorage<ReplayPreference>(
    user ? SESSION_REPLAY_PREFERENCE_KEY + '_' + user.id : 'temp_key',
    'loading',
    { initializeWithValue: false }
  );

  // Update session recording config when preference changes
  useEffect(() => {
    if (!initialized.current || !user || replayPreference === 'loading') return;

    const maskTextSelector =
      replayPreference !== 'full-opt-in'
        ? '.agent-run-viewer, .metadata, .agent-run-table'
        : '';

    posthogClient.set_config({
      session_recording: {
        maskAllInputs: true,
        maskInputFn,
        maskTextSelector,
      },
    });
  }, [replayPreference, user]);

  return <PostHogProvider client={posthogClient}>{children}</PostHogProvider>;
}

export function ReduxProvider({ children }: { children: React.ReactNode }) {
  return <Provider store={store}>{children}</Provider>;
}
