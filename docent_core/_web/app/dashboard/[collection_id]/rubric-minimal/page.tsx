'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  useCreateRubricMutation,
  useGetJudgeModelsQuery,
  useStartEvaluationMutation,
} from '@/app/api/rubricApi';
import type { ModelOption } from '@/app/store/rubricSlice';
import { toast } from 'sonner';
import MinimalQuickSearchBox from './components/MinimalQuickSearchBox';
import ModelPicker from '@/components/ModelPicker';

const DEFAULT_MINIMAL_SCHEMA = {
  type: 'object',
  required: ['label', 'explanation'],
  properties: {
    label: { type: 'string', enum: ['match', 'no match'] },
    explanation: { type: 'string', citations: true },
  },
};

const isGpt5Mini = (model: ModelOption): boolean =>
  model.provider === 'openai' &&
  model.reasoning_effort === 'medium' &&
  (model.model_name === 'gpt-5-mini' || model.model_name === 'gpt5-mini');

const isGpt5 = (model: ModelOption): boolean =>
  model.provider === 'openai' &&
  model.reasoning_effort === 'medium' &&
  model.model_name === 'gpt-5';

export default function RubricMinimalPage() {
  const router = useRouter();
  const { collection_id: collectionId } = useParams<{
    collection_id: string;
  }>();

  const { data: availableJudgeModels } = useGetJudgeModelsQuery();
  const minimalJudgeModels = useMemo(() => {
    if (!availableJudgeModels) return [];

    const gpt5Mini = availableJudgeModels.find(isGpt5Mini);
    const gpt5 = availableJudgeModels.find(isGpt5);
    return [gpt5Mini, gpt5].filter((model): model is ModelOption =>
      Boolean(model)
    );
  }, [availableJudgeModels]);

  const [selectedJudgeModel, setSelectedJudgeModel] = useState<
    ModelOption | undefined
  >(undefined);

  useEffect(() => {
    if (minimalJudgeModels.length === 0) return;

    setSelectedJudgeModel((previous) => {
      if (!previous) return minimalJudgeModels[0];

      const stillAllowed = minimalJudgeModels.some(
        (candidate) =>
          candidate.provider === previous.provider &&
          candidate.model_name === previous.model_name &&
          candidate.reasoning_effort === previous.reasoning_effort
      );
      return stillAllowed ? previous : minimalJudgeModels[0];
    });
  }, [minimalJudgeModels]);

  const [createRubric, { isLoading: isCreatingRubric }] =
    useCreateRubricMutation();
  const [startEvaluation, { isLoading: isStartingEvaluation }] =
    useStartEvaluationMutation();

  const handleDirectSubmit = async (
    highLevelDescription: string,
    _useComments: boolean
  ) => {
    if (!collectionId) return;

    if (!selectedJudgeModel) {
      toast.error('Judge model is still loading.');
      return;
    }

    try {
      const rubricId = await createRubric({
        collectionId,
        rubric: {
          rubric_text: highLevelDescription,
          output_schema: DEFAULT_MINIMAL_SCHEMA,
          judge_model: selectedJudgeModel,
        },
      }).unwrap();

      await startEvaluation({
        collectionId,
        rubricId,
        max_agent_runs: null,
        n_rollouts_per_input: 1,
        filter: null,
        max_parallel: null,
      }).unwrap();

      router.push(`/dashboard/${collectionId}/rubric-minimal/${rubricId}`);
    } catch (error) {
      console.error('Failed to create and run minimal rubric flow', error);
      toast.error('Failed to run direct search');
    }
  };

  const isLoading = isCreatingRubric || isStartingEvaluation;

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-background rounded-lg border p-3">
      <MinimalQuickSearchBox
        onDirect={handleDirectSubmit}
        isLoading={isLoading}
        modelPicker={
          selectedJudgeModel ? (
            <ModelPicker
              selectedModel={selectedJudgeModel}
              availableModels={minimalJudgeModels}
              onChange={setSelectedJudgeModel}
              className="w-32"
              borderless
              shortenName
            />
          ) : null
        }
      />
    </div>
  );
}
