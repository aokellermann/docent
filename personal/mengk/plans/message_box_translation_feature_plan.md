# Message Box Translation Feature Plan

## Goal
Add an on-demand translation flow to each transcript message box in the Agent Run viewer.

Requested behavior:
- Every message box has translation controls.
- Default translation target is English.
- Users can choose other target languages.
- Translation output is rendered in a separate UI area and does not alter the original message content/citation rendering.
- Backend uses a simple non-streaming LLM call for translation.
- Backend changes must be in:
  - `docent_core/docent/services/monoservice.py`
  - `docent_core/docent/server/rest/router.py`
- Frontend RTK change must be in:
  - `docent_core/_web/app/api/collectionApi.ts`

## Current Code Discovery

### 1) Message rendering location and constraints
- `MessageBox` is the per-message component in the Agent Run transcript UI: `docent_core/_web/app/dashboard/[collection_id]/agent_run/components/MessageBox.tsx:183`.
- Main message text is already normalized via `getMainTextContent(message)`: `docent_core/_web/app/dashboard/[collection_id]/agent_run/components/MessageBox.tsx:107`.
- Existing right-side controls in header row include telemetry, Pretty JSON toggle, and metadata popover: `docent_core/_web/app/dashboard/[collection_id]/agent_run/components/MessageBox.tsx:542`.
- Main content rendering is separate and citation-aware (`SegmentedText`): `docent_core/_web/app/dashboard/[collection_id]/agent_run/components/MessageBox.tsx:384`.

Implication: translation UI should be added alongside existing header controls, and translated output should render below main content in a separate block.

### 2) Existing RTK API conventions
- Collection-level API endpoints are in `collectionApi`: `docent_core/_web/app/api/collectionApi.ts:106`.
- Mutations follow `build.mutation<Resp, Req>({ query: (...) => ({ url, method, body }) })` patterns, e.g. `generateDql`: `docent_core/_web/app/api/collectionApi.ts:340`.
- Hook exports are appended at bottom destructure export block: `docent_core/_web/app/api/collectionApi.ts:440`.

### 3) Router conventions for collection-scoped endpoints
- Collection-scoped read endpoints live in `router.py` with `ctx: ViewContext = Depends(get_default_view_ctx)` and `require_view_permission(Permission.READ)`, e.g. `get_agent_run`: `docent_core/docent/server/rest/router.py:898`.
- Request bodies are modeled with Pydantic `BaseModel` in the same file, e.g. `AgentRunMetadataRequest`: `docent_core/docent/server/rest/router.py:991`.

### 4) Existing dependency for LLM service
- `get_llm_svc` already exists and returns `LLMService`: `docent_core/docent/server/dependencies/services.py:40`.
- `router.py` currently imports only `MonoService` from services, not `get_llm_svc`.

### 5) Existing non-streaming LLM usage style
- In `DQLGeneratorService`, non-streaming call pattern is:
  - `outputs = await self.llm_svc.get_completions(...)`: `docent_core/docent/services/dql_generator.py:353`
  - read `result = outputs[0]`, guard `result.did_error`/empty `result.first.text`: `docent_core/docent/services/dql_generator.py:361`
- Provider preferences singleton is `PROVIDER_PREFERENCES`; default chat model set exists at `default_chat_models`: `docent_core/docent/services/llms.py:258`.

### 6) MonoService currently has no LLM dependency
- `MonoService.__init__(self, db: DocentDB)` only stores DB: `docent_core/docent/services/monoservice.py:245`.

Implication: to keep change minimal and scoped to requested files, new MonoService translation method should accept `llm_svc` as a method argument (instead of refactoring MonoService constructor/dependency wiring globally).

## Proposed Design

## API Contract
Add a new endpoint in `router.py`:
- Method/path: `POST /rest/{collection_id}/translate_message`
- Auth/permissions: same read gate as transcript fetch (`require_view_permission(Permission.READ)`)
- Request JSON:
  - `text: str` (required)
  - `target_language: str = "English"`
  - `source_language: str | None = None` (optional; `None` means auto-detect)
- Response JSON:
  - `translated_text: str`
  - `target_language: str`

Reasoning:
- Explicit request/response keeps frontend straightforward.
- Optional `source_language` leaves room for manual source override while preserving default “translate whatever language to English”.

## Backend service behavior
In `MonoService`, add a new method that builds a minimal prompt and performs one non-streaming LLM call:
- Validate `text.strip()` and `target_language.strip()`.
- Construct messages using existing chat message models.
- Prompt instructs model to return only translated text (no explanations).
- Use `llm_svc.get_completions` with conservative settings:
  - `model_options=PROVIDER_PREFERENCES.default_chat_models`
  - `temperature=0.0`
  - `max_new_tokens` around `2048`
  - `use_cache=True`
- Validate model output and return trimmed translation.
- Raise `ValueError` for invalid input or unusable model output so router can return HTTP 400.

## Frontend UI behavior
In each `MessageBox`:
- Add target language dropdown (default `English`).
- Add `Translate` button.
- On click, call RTK mutation with `collectionId` from `dataContext.collection_id` and `text` from `mainTextContent`.
- Render translation in a dedicated block below the original message body.
- Keep original content/citation rendering untouched.
- Show loading state, and non-blocking error text inside the translation block if translation fails.

## Minimal language list
Use a static array in `MessageBox.tsx` for now (simple and deterministic):
- English (default), Spanish, French, German, Portuguese, Italian, Japanese, Korean, Chinese (Simplified), Chinese (Traditional), Arabic, Hindi, Russian.

This satisfies “select other languages as well” without adding backend metadata endpoints.

## Step-by-Step Implementation Plan

### Step 1: Add MonoService translation method
File: `docent_core/docent/services/monoservice.py`

1. Add imports:
- `from docent.data_models.chat.message import SystemMessage, UserMessage`
- `from docent_core.docent.services.llms import LLMService, PROVIDER_PREFERENCES`

2. Add method on `MonoService` (new public method):

```python
async def translate_text(
    self,
    *,
    llm_svc: LLMService,
    text: str,
    target_language: str = "English",
    source_language: str | None = None,
) -> str:
    if not text.strip():
        raise ValueError("text must be non-empty")
    if not target_language.strip():
        raise ValueError("target_language must be non-empty")

    source_hint = source_language.strip() if source_language else "auto-detect"
    system_prompt = (
        "You are a translation assistant. "
        "Translate the user-provided text into the requested target language. "
        "Return only the translated text. Do not add explanations, quotes, or metadata."
    )
    user_prompt = (
        f"Source language: {source_hint}\n"
        f"Target language: {target_language.strip()}\n\n"
        "Text to translate:\n"
        f"{text}"
    )

    outputs = await llm_svc.get_completions(
        inputs=[[SystemMessage(content=system_prompt), UserMessage(content=user_prompt)]],
        model_options=PROVIDER_PREFERENCES.default_chat_models,
        max_new_tokens=2048,
        temperature=0.0,
        use_cache=True,
    )

    result = outputs[0]
    if result.did_error or result.first is None or not result.first.text:
        raise ValueError("Translation failed. Model returned no text.")

    translated = result.first.text.strip()
    if not translated:
        raise ValueError("Translation failed. Empty output.")
    return translated
```

Notes:
- This keeps LLM behavior encapsulated in `MonoService` as requested.
- No DB writes, no session changes.

### Step 2: Add translation endpoint and request/response models
File: `docent_core/docent/server/rest/router.py`

1. Import dependency:
- Add `get_llm_svc` to imports from `docent_core.docent.server.dependencies.services`.
- Import `LLMService` type from `docent_core.docent.services.llms` (optional but recommended for type clarity).

2. Add request/response models near other collection models:

```python
class TranslateMessageRequest(BaseModel):
    text: str
    target_language: str = "English"
    source_language: str | None = None


class TranslateMessageResponse(BaseModel):
    translated_text: str
    target_language: str
```

3. Add new endpoint near agent-run read endpoints (around `get_agent_run` section):

```python
@user_router.post("/{collection_id}/translate_message", response_model=TranslateMessageResponse)
async def translate_message(
    request: TranslateMessageRequest,
    mono_svc: MonoService = Depends(get_mono_svc),
    llm_svc: LLMService = Depends(get_llm_svc),
    ctx: ViewContext = Depends(get_default_view_ctx),
    _: None = Depends(require_view_permission(Permission.READ)),
) -> TranslateMessageResponse:
    try:
        translated = await mono_svc.translate_text(
            llm_svc=llm_svc,
            text=request.text,
            target_language=request.target_language,
            source_language=request.source_language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return TranslateMessageResponse(
        translated_text=translated,
        target_language=request.target_language,
    )
```

Notes:
- Keep permissions at READ because source text is from a readable transcript.
- No streaming response per requirement.

### Step 3: Add RTK mutation for translation
File: `docent_core/_web/app/api/collectionApi.ts`

1. Add request/response interfaces:

```ts
interface TranslateMessageRequest {
  collectionId: string;
  text: string;
  target_language?: string;
  source_language?: string | null;
}

interface TranslateMessageResponse {
  translated_text: string;
  target_language: string;
}
```

2. Add mutation endpoint under `endpoints`:

```ts
translateMessage: build.mutation<
  TranslateMessageResponse,
  TranslateMessageRequest
>({
  query: ({ collectionId, ...body }) => ({
    url: `/${collectionId}/translate_message`,
    method: 'POST',
    body,
  }),
}),
```

3. Export hook at bottom:
- Add `useTranslateMessageMutation` to exported hooks list.

### Step 4: Add translation controls and result panel to MessageBox
File: `docent_core/_web/app/dashboard/[collection_id]/agent_run/components/MessageBox.tsx`

1. Update imports:
- React hooks: include `useState`.
- RTK hook: `useTranslateMessageMutation` from `@/app/api/collectionApi`.
- UI controls: `Button`, `Select`, `SelectTrigger`, `SelectContent`, `SelectItem`, `SelectValue`.

2. Add local constants/state in component:
- `const DEFAULT_TARGET_LANGUAGE = 'English';`
- language options array.
- state:
  - `targetLanguage`
  - `translatedText`
  - `translationError`
- mutation tuple:
  - `const [translateMessage, { isLoading: isTranslating }] = useTranslateMessageMutation();`

3. Add click handler:

```ts
const handleTranslate = async () => {
  setTranslationError(null);
  try {
    const result = await translateMessage({
      collectionId,
      text: mainTextContent,
      target_language: targetLanguage,
      source_language: null,
    }).unwrap();
    setTranslatedText(result.translated_text);
  } catch (error) {
    setTranslationError('Translation failed. Please try again.');
  }
};
```

4. Add controls in header right section (same area as Pretty JSON/metadata):
- `Select` for target language.
- `Button` for translate/re-translate.
- Disable translate button when:
  - no `mainTextContent.trim()`
  - `isTranslating`

5. Render separate translation area after main body and before/after tool info (either works; recommended after main text and before tool sections for readability):

```tsx
{(isTranslating || translatedText || translationError) && (
  <div className="mt-2 p-2 rounded border border-indigo-border bg-indigo-bg space-y-2">
    <div className="text-[10px] text-indigo-text">Translation ({targetLanguage})</div>
    {isTranslating && <div className="text-xs text-muted-foreground">Translating...</div>}
    {translationError && <div className="text-xs text-red-text">{translationError}</div>}
    {translatedText && (
      <div className="whitespace-pre-wrap [overflow-wrap:anywhere] text-xs font-mono text-primary">
        {translatedText}
      </div>
    )}
  </div>
)}
```

Important:
- Do not replace `renderMainMessageContent()` output.
- Do not pass translated text into citation logic.
- Keep translation panel purely additive.

### Step 5: Verification

1. Backend static checks:
- `source .venv/bin/activate && pyright docent_core/docent/services/monoservice.py docent_core/docent/server/rest/router.py`

2. Frontend lint/type check:
- `cd docent_core/_web && npm run lint`

3. Manual functional check:
- Open Agent Run viewer.
- For a message with non-English text:
  - Target defaults to English.
  - Click Translate -> translated output appears in separate area.
- Change target language (e.g., Spanish) and re-translate.
- Confirm original content remains unchanged and citation highlighting still functions.
- Confirm button disabled for empty-text messages.

## Edge Cases and Handling
- Empty message text: return backend 400; frontend disables button to avoid request.
- LLM returns empty content/error: backend converts to 400 with user-facing detail.
- Very long text: initial implementation sends full text; if latency/cost becomes problematic, add a hard cap in follow-up.
- Messages containing JSON/code: translated output stays separate; original content and Pretty JSON behavior are unaffected.

## Assumptions
- Translation applies to the message main text only (`getMainTextContent`) and not reasoning/tool-call blocks.
- Static language option list in UI is acceptable for v1.
- Using `PROVIDER_PREFERENCES.default_chat_models` is acceptable for this new lightweight feature (no dedicated translation preference needed yet).

## Risks
- Translation quality variability across model fallback chain.
- Cost increase from ad hoc per-message translation requests.
- If models occasionally return extra prose despite prompt, output may include non-translation text; prompt is intentionally strict to minimize this.

## Out-of-Scope (for this request)
- Persisting translations in DB.
- Translation history/versioning.
- Auto-translate all messages on load.
- Streaming translation responses.
