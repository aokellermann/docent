import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import { refinementApi } from '@/app/api/refinementApi';
import { ChatMessage } from '@/app/types/transcriptTypes';

interface RefinementState {
  messages: ChatMessage[];
}

const initialState: RefinementState = {
  messages: [],
};

const refinementSlice = createSlice({
  name: 'refinement',
  initialState,
  reducers: {
    setMessages: (state, action: PayloadAction<ChatMessage[]>) => {
      state.messages = action.payload;
    },
    appendMessage: (state, action: PayloadAction<ChatMessage>) => {
      state.messages.push(action.payload);
    },
  },
  extraReducers: (builder) => {
    builder.addMatcher(
      refinementApi.endpoints.getCurrentState.matchFulfilled,
      (state, { payload }) => {
        state.messages = payload.messages;
      }
    );
    // match the rsession in the postmessage mutation
    builder.addMatcher(
      refinementApi.endpoints.postMessageToRefinementSession.matchFulfilled,
      (state, { payload }) => {
        state.messages = payload?.rsession?.messages ?? [];
      }
    );
  },
});

export const { setMessages, appendMessage } = refinementSlice.actions;
export default refinementSlice.reducer;
