import { ModeToggle } from '@/components/ui/theme-toggle';
import { BookText, ChevronRight, Layers, MessageCircle } from 'lucide-react';
import Link from 'next/link';
import {
  useRouter,
  useParams,
  useSearchParams,
  usePathname,
} from 'next/navigation';
import { useSelector } from 'react-redux';

import { BASE_DOCENT_PATH } from '@/app/constants';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import { RootState } from '../store/store';
import { UserProfile } from './auth/UserProfile';
import ShareViewPopover from '@/lib/permissions/ShareViewPopover';

const Breadcrumbs: React.FC = () => {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const pathname = usePathname();

  const collectionId = useSelector(
    (state: RootState) => state.collection.collectionId
  );

  // check if we are "home", i.e. at /dashboard/[collection_id]
  const effectiveCollectionId =
    collectionId || (params?.collection_id as string | undefined);
  const normalizePath = (p?: string | null) => (p ? p.replace(/\/+$/, '') : '');
  const isHome =
    !!effectiveCollectionId &&
    normalizePath(pathname) ===
      normalizePath(`${BASE_DOCENT_PATH}/${effectiveCollectionId}`);

  // Get the current page information
  const agentRunId = params?.agent_run_id as string | undefined;
  const refinementSessionId = params?.session_id as string | undefined;

  return (
    <div className="_Breadcrumbs text-sm flex items-center justify-between w-full">
      <div className="flex items-center gap-x-3">
        {/* Go Home button */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs whitespace-nowrap px-2 py-0 flex items-center gap-x-1"
              onClick={() => router.push('/dashboard')}
            >
              <Layers size={14} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>See all Collections</p>
          </TooltipContent>
        </Tooltip>

        {/* Breadcrumbs */}
        <div className="flex gap-x-1 items-center">
          {/* Home link */}
          {isHome ? (
            <span className="text-muted-foreground">All agent runs</span>
          ) : (
            <Link
              href={`${BASE_DOCENT_PATH}/${effectiveCollectionId}`}
              className="text-blue-text hover:underline"
            >
              All agent runs
            </Link>
          )}

          {/* Transcript page */}
          {agentRunId && (
            <>
              <ChevronRight size={18} />
              <span className="text-muted-foreground">
                Agent run {agentRunId}
              </span>
            </>
          )}

          {refinementSessionId && (
            <>
              <ChevronRight size={18} />
              <span className="text-muted-foreground">
                Refinement session {refinementSessionId}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-x-2">
        <Button
          variant="outline"
          size="sm"
          className="gap-x-2 h-7 cursor-default px-2"
        >
          <Link
            href="https://docs.transluce.org"
            target="_blank"
            className="flex items-center gap-x-2"
          >
            <BookText size={14} />
            Docs
          </Link>
        </Button>

        <Button
          variant="outline"
          size="sm"
          className="gap-x-2 h-7 cursor-default px-2"
        >
          <Link
            href="https://transluce.org/docent/slack"
            target="_blank"
            className="flex items-center gap-x-2"
          >
            <MessageCircle size={14} />
            Slack
          </Link>
        </Button>

        {/* Share view */}
        {collectionId && <ShareViewPopover collectionId={collectionId} />}

        {/* Embeddings */}
        {/* <EmbeddingsPopover /> */}

        {/* Connection status */}
        {/* <Button
          variant="outline"
          size="sm"
          className="gap-x-2 h-7 cursor-default px-2 pointer-events-none"
        >
          <div
            className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-green-text' : 'bg-red-text'}`}
          />
          {isConnected ? 'Connected' : 'Disconnected'}
        </Button> */}
        <ModeToggle />
        <UserProfile />
      </div>
    </div>
  );
};

export default Breadcrumbs;
