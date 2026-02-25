## Build `/rubric-minimal`: Minimal Rubric Search + Transcript Viewer Flow

### Summary
Add a new, URL-only parallel rubric flow under `/dashboard/[collection_id]/rubric-minimal` that is optimized for first-time hackathon users:
- Left side: minimal search controls + results list
- Right side: transcript viewer only
- No guided flow, presets, label sets, output schema editing, or transcript chat panel
- Direct search executes immediately with default run settings

This will not change existing `/rubric` behavior.

### Route and UI Architecture
1. Add a new route tree parallel to existing rubric routes:
   - `docent_core/_web/app/dashboard/[collection_id]/rubric-minimal/page.tsx`
   - `docent_core/_web/app/dashboard/[collection_id]/rubric-minimal/[rubric_id]/layout.tsx`
   - `docent_core/_web/app/dashboard/[collection_id]/rubric-minimal/[rubric_id]/page.tsx`
   - `docent_core/_web/app/dashboard/[collection_id]/rubric-minimal/[rubric_id]/agent_run/[agent_run_id]/page.tsx`
   - `docent_core/_web/app/dashboard/[collection_id]/rubric-minimal/[rubric_id]/agent_run/[agent_run_id]/result/[result_id]/page.tsx`

2. Keep this route URL-only:
   - Do **not** add a sidebar menu item.
   - Add section-title support in `docent_core/_web/app/dashboard/[collection_id]/client-layout.tsx` so page title is correct for `rubric-minimal`.

3. Reuse existing providers where possible:
   - `RubricVersionProvider`, `CitationNavigationProvider`, and existing rubric data APIs.
   - Create a minimal layout variant that excludes refine/analyze right tabs entirely.

### Component Changes (Feature-Flagged for Reuse)
1. `QuickSearchBox` (or minimal wrapper):
   - Add props to allow hiding guided/presets.
   - In minimal mode:
     - hide “Try a preset”
     - hide guided button
     - show only “Direct search”
     - smaller rubric textarea default height (e.g. ~`h-24` instead of `h-48`)

2. Minimal entry page (`rubric-minimal/page.tsx`):
   - Show only quick search + model picker (no output schema panel, no rubric list).
   - Model options hard-limited to:
     - `openai/gpt5-mini` with `reasoning_effort: "medium"` (default)
     - `openai/gpt-5` with `reasoning_effort: "medium"`
   - On direct search click:
     - create rubric using default schema
     - create/get direct session
     - immediately call `startEvaluation` with defaults:
       - `max_agent_runs: null` (all)
       - `filter: null`
       - `n_rollouts_per_input: 1`
       - `label_set_id: undefined`
       - `max_parallel: null` (server default behavior)
     - navigate to `/dashboard/[collection_id]/rubric-minimal/[rubric_id]`

3. `SingleRubricArea` + `RubricEditor` minimal mode support:
   - Add explicit props (e.g. `mode?: 'default' | 'minimal'`) to hide advanced features.
   - In minimal mode:
     - remove label set controls/dialog and agreement UI
     - remove filter controls/chips/actions
     - remove clustering controls
     - remove download menu
     - remove failures toggle if it relies on advanced controls
     - keep only rubric text + model picker + direct search action + results list
   - Replace run dialog behavior in minimal mode:
     - direct search triggers immediate `startEvaluation` defaults
     - no `RubricRunDialog` open path

4. Results list navigation support:
   - `JudgeResultCard` currently hardcodes `/rubric/...` routes.
   - Add a route-base prop (e.g. `routeBase: 'rubric' | 'rubric-minimal'`) and thread through:
     - `JudgeResultsList`
     - `PaginatedResultsList`
     - `JudgeResultCard`
   - Use `rubric-minimal` base in minimal flow so clicks stay inside minimal route.

5. `AgentRunViewer` minimal behavior:
   - Add prop for initial transcript navigator visibility (e.g. `defaultSidebarVisible?: boolean`).
   - In minimal result pages, pass `false` so folder tree is hidden by default.
   - Keep existing toggle button so it can still be opened if needed.

6. Minimal rubric result layout:
   - Left panel: minimal `SingleRubricArea`.
   - Middle panel: existing `AgentRunViewer` route content.
   - No right panel (`TranscriptChat` removed entirely for minimal mode).

### Public API / Interfaces / Types
1. Add optional UI-mode props to shared components:
   - `QuickSearchBox`
   - `SingleRubricArea`
   - `RubricEditor`
   - `JudgeResultsList` / `PaginatedResultsList` / `JudgeResultCard`
   - `AgentRunViewer`
2. No backend API contract changes.
3. No DB schema or migration changes.

### Default Behavior for Minimal Mode
1. Search run defaults:
   - all agent runs
   - unfiltered
   - one rollout per agent run
2. Model defaults:
   - default selected model: `gpt5-mini` (medium reasoning effort)
   - second option: `gpt-5` (medium reasoning effort)
3. Output schema:
   - fixed default schema used today (`label` + `explanation`)
   - hidden from UI in minimal flow

### Test Cases and Scenarios
1. Route smoke tests (frontend integration/e2e or component-level with router mocks):
   - `/dashboard/:id/rubric-minimal` renders minimal input page
   - `/dashboard/:id/rubric-minimal/:rubric_id` renders minimal left panel without advanced controls
   - result navigation remains under `/rubric-minimal/...`

2. Direct search execution test:
   - clicking direct search triggers `createRubric` then `startEvaluation` with expected default payload
   - no run dialog is opened

3. UI visibility assertions (minimal mode):
   - no presets, no guided search, no output schema panel, no label set UI, no transcript chat panel
   - transcript navigator hidden on first load in `AgentRunViewer`

4. Model selection tests:
   - only two allowed models present
   - default is `gpt5-mini (medium)`

5. Regression checks for existing `/rubric`:
   - guided + preset + schema + label set + run dialog behavior unchanged in default mode

6. Required quality checks:
   - `npm run lint` in `docent_core/_web/` with zero errors after changes

### Assumptions and Locked Decisions
1. `/rubric-minimal` is a **full parallel flow** (entry + detail + result routes).
2. Direct search on minimal entry page **creates and runs immediately**.
3. Transcript chat panel is **hidden entirely** (not toggleable) in minimal flow.
4. `/rubric-minimal` is **URL-only** (no sidebar link).
5. Existing `/rubric` and backend behavior remain unchanged outside optional component props.
