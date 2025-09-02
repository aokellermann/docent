'use client';

import { useParams, useRouter } from 'next/navigation';
import { v4 as uuidv4 } from 'uuid';

import { Card } from '@/components/ui/card';

import RubricList from './RubricList';
import {
  useStartEvaluationMutation,
  useCreateRubricMutation,
} from '../../../api/rubricApi';
import { useCreateOrGetRefinementSessionMutation } from '../../../api/refinementApi';
import { toast } from '@/hooks/use-toast';
import QuickSearchBox from './QuickSearchBox';

const RubricArea = () => {
  const router = useRouter();
  const params = useParams();
  const collectionId = params.collection_id as string;

  // Handle starting evaluations
  const [startEvaluation] = useStartEvaluationMutation();
  const handleEvaluate = async (rubricId: string) => {
    // First start the job
    await startEvaluation({
      collectionId,
      rubricId,
    });
  };

  /**
   * Quick search box
   */

  const [createRubric, { isLoading: isCreatingRubric }] =
    useCreateRubricMutation();
  const [createOrGetSession, { isLoading: isCreatingOrGettingSession }] =
    useCreateOrGetRefinementSessionMutation();
  const handleAddNewRubric = async (rubricText: string) => {
    if (!collectionId) return undefined;

    try {
      // Create a new rubric using the API
      const rubricId = uuidv4();
      const newRubric = {
        rubric_text: rubricText,
        id: rubricId,
      };

      await createRubric({
        collectionId,
        rubric: newRubric,
      }).unwrap();

      return rubricId;
    } catch (error) {
      console.error('Failed to create rubric:', error);
      toast({
        title: 'Error',
        description: 'Failed to create rubric',
        variant: 'destructive',
      });
    }
  };

  const handleQuickSearchSubmit = async (
    highLevelDescription: string,
    mode: 'explore' | 'full'
  ) => {
    if (mode === 'explore') {
      const rubricId = await handleAddNewRubric(highLevelDescription);
      if (!rubricId || !collectionId) return;
      try {
        const res = await createOrGetSession({
          collectionId,
          rubricId,
        }).unwrap();
        router.push(`/dashboard/${collectionId}/refine/${res.id}`);
      } catch (error) {
        console.error('Failed to start refinement session:', error);
        toast({
          title: 'Error',
          description: 'Failed to start refinement session',
          variant: 'destructive',
        });
      }
    } else {
      const rubricId = await handleAddNewRubric(highLevelDescription);
      if (rubricId) {
        handleEvaluate(rubricId);
        // Then redirect to the rubric page
        router.push(`/dashboard/${collectionId}/rubric/${rubricId}`);
      }
    }
  };

  return (
    <Card className="h-full flex overflow-y-auto flex-col flex-1 p-3 custom-scrollbar space-y-3">
      {/* Rubric Display */}
      <div className="space-y-2">
        <QuickSearchBox
          onSubmit={handleQuickSearchSubmit}
          isLoading={isCreatingRubric || isCreatingOrGettingSession}
        />
        <RubricList />
      </div>
    </Card>
  );
};

export default RubricArea;
