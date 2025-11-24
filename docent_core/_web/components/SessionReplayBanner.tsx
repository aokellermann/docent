'use client';

import { Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ReplayPreference } from '@/app/types/userTypes';
import { useLocalStorage } from 'usehooks-ts';
import { SESSION_REPLAY_PREFERENCE_KEY } from '@/app/constants';
import { usePostHog as usePostHogClient } from 'posthog-js/react';
import { useRequireUserContext } from '@/app/contexts/UserContext';

export default function SessionReplayBanner() {
  const posthog = usePostHogClient();
  const { user } = useRequireUserContext();

  const [replayPreference, setReplayPreference] =
    useLocalStorage<ReplayPreference>(
      SESSION_REPLAY_PREFERENCE_KEY + '_' + user.id,
      'loading',
      { initializeWithValue: false }
    );

  const handleFullOptIn = () => {
    setReplayPreference('full-opt-in');
    posthog.startSessionRecording();
  };

  const handleMaskedOptIn = () => {
    setReplayPreference('masked-opt-in');
    posthog.startSessionRecording();
  };

  const handleOptOut = () => {
    setReplayPreference('opted-out');
    posthog.stopSessionRecording();
  };

  // Don't render until PostHog is initialized on the client
  if (replayPreference === 'loading' || replayPreference !== 'not-set') {
    return null;
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-blue-bg border-b border-blue-border">
      <div className="max-w-7xl mx-auto px-4 py-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1">
            <p className="text-sm text-primary">
              We use PostHog to catch bugs and understand which features you
              enjoy. As a small team, we find these insights really helpful for
              prioritizing what to build next. We anonymize all analytics and
              mask sensitive data.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={handleFullOptIn} size="sm" variant="outline">
              Accept All
            </Button>
            <Button onClick={handleOptOut} size="sm" variant="outline">
              Decline All
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button size="sm" variant="ghost" className="text-primary">
                  <Info className="mr-2 h-4 w-4" />
                  Manage Settings
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl">
                <DialogHeader>
                  <DialogTitle>Manage Settings</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 text-sm">
                  <p>
                    We use screen capture to see how you work with Docent and
                    make it better for you.
                  </p>

                  <p>
                    <strong>Privacy:</strong> All session recordings are
                    anonymous. Only the Docent team sees your data. We will
                    never sell your data or track you outside of Docent. All
                    session recordings are deleted within 90 days. Change your
                    preference anytime in Settings / Privacy.
                  </p>

                  <div className="space-y-2">
                    <p className="font-bold">Full Session Replay</p>
                    <ul className="list-disc pl-5 space-y-1">
                      <li>
                        Included: transcripts, metadata, and rubrics visible on
                        your screen
                      </li>
                      <li>Hidden: passwords, API keys, emails</li>
                    </ul>
                  </div>

                  <div className="space-y-2">
                    <p className="font-bold">Masked Session Replay</p>
                    <ul className="list-disc pl-5 space-y-1">
                      <li>Included: rubrics and which features you click</li>
                      <li>
                        Hidden: transcripts, agent runs, metadata, passwords and
                        personal data
                      </li>
                    </ul>
                  </div>

                  <p>
                    Working with sensitive data? Email{' '}
                    <a
                      href="mailto:docent@transluce.org"
                      className="underline hover:text-primary"
                    >
                      docent@transluce.org
                    </a>{' '}
                    and we&apos;ll help you self-host.
                  </p>
                </div>
                <DialogFooter className="sm:justify-start border-t pt-4">
                  <Button onClick={handleFullOptIn} size="sm">
                    Accept Full Recording
                  </Button>
                  <Button onClick={handleMaskedOptIn} size="sm">
                    Accept Masked Recording
                  </Button>
                  <Button onClick={handleOptOut} size="sm">
                    Decline All
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    </div>
  );
}
