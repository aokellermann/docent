/**
 * Note(mengk): the patterns in this file are highly deprecated!
 * This is not very "React-ive" - having global state like this and using async thunks is highly discouraged.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

export interface StreamedEmbeddingResult {
  indexing_phase: string;
  embedding_progress: number;
  indexing_progress: number;
}

export interface EmbedState {
  embeddingProgress?: StreamedEmbeddingResult;
  isListening?: boolean;
}

const initialState: EmbedState = {};

export const embedSlice = createSlice({
  name: 'embed',
  initialState,
  reducers: {
    setEmbeddingProgress: (
      state,
      action: PayloadAction<StreamedEmbeddingResult | undefined>
    ) => {
      state.embeddingProgress = action.payload;
    },
    setIsListening: (state, action: PayloadAction<boolean>) => {
      state.isListening = action.payload;
    },
    resetEmbedSlice: () => initialState,
  },
});

export const { setEmbeddingProgress, setIsListening, resetEmbedSlice } =
  embedSlice.actions;

export default embedSlice.reducer;
