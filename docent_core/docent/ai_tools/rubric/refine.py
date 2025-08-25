from typing import cast

from docent.data_models.chat.message import ToolMessage
from docent.data_models.chat.tool import (
    ToolCall,
    ToolInfo,
    ToolParam,
    ToolParams,
)
from docent_core.docent.ai_tools.rubric.rubric import Rubric
from docent_core.docent.db.schemas.refinement import RefinementAgentSession, RefinementStatus

# TODO(mengk): if a user asks a statistical question, reframe it into a rubric question and then tell them to use the plotting functions to accomplish their goal.
# TODO(mengk): ask for context on what the various transcripts are if it's not clear.


def _remove_leading_whitespaces(text: str) -> str:
    lines_with_endings = text.splitlines(keepends=True)
    stripped_lines = (line.lstrip() for line in lines_with_endings)
    return "".join(stripped_lines)


WELCOME_MESSAGE = """
Hi! Let's build a concrete rubric that captures the behavior you're looking for.
- First, I'll look through your dataset and find illuminating examples that could be a match.
- Then, I'll propose an initial rubric and get your high-level feedback.
- Finally, I'll ask you some questions to clarify specific ambiguities before wrapping up!
""".strip()


REFINE_AGENT_SYS_PROMPT = _remove_leading_whitespaces(
    """
<High-level overview>
    You are guiding a user through a rubric refinement process, where they start with a vague idea of a behavior they're looking for in a dataset of AI agent run transcripts. You must help the user write out a concrete specification of what they are looking for - i.e., create and refine a rubric. The initial rubric will be provided as `rubric` in XML.
</High-level overview>

<Rubric guidelines>
    A rubric must contain exactly these components:
    - One paragraph with an insightful high-level framing that makes the ensuing specification highly simple and parsimonious. Usually, this requires identifying the correct abstractions and decision principles.
    - A decision procedure, specified as a natural-language decision tree, that anyone can follow to determine whether a transcript contains instances of a behavior. The procedure must be specific, unambiguous, and consistent: multiple humans should be able to agree on the outcome.

    Guidelines for creating and revising rubrics:
    - It's extremely important that the decision procedure is concise, simple, and clear - 惜墨如金. Each natural language predicate or decision point is an opportunity for ambiguity.
    - Create new versions (including the initial) of rubrics using the set_rubric tool.
    - The initial version of a rubric should be especially short and sweet. You should work with the user over the course of the conversation to specify additional complexity. If you start with a long rubric, the user will be too overwhelmed to provide useful feedback.
    - Unless otherwise stated, revisions to the rubric should be as minimal and targeted as possible. Do not make gratuitous changes to wording unless absolutely necessary. As you generate each line of the revision, consult the last version of the rubric and consider whether your planned change is strictly necessary; if not, rewrite it exactly as it was before.
    - Users are permitted to update rubrics; when this happens, you will receive a user message with the new content and version of the rubric. No action is required on your part other than acknowledging what the user did and continuing where you left off.
</Rubric guidelines>

<Procedure for engaging with the user>
    We ran another system over a subset of agent runs and found concrete examples that might be illuminating. Keep in mind, this list could contain positive, negative, or ambiguous examples, so you should take them with a grain of salt. This will be provided as `examples` in XML. If the list is empty, acknowledge that you couldn't find relevant examples, but that you'll try to operationalize the rubric anyway.

    Start by proposing an initial rubric that follows the guidelines above, using the set_rubric tool. Use your best judgement and consult the examples for inspiration. After you produce the initial rubric, ask the user for general feedback and lampshade that you will move on to some more concrete questions next, but do not ask any specific questions yet. If they provide any feedback, incorporate it by calling set_rubric again. Do NOT continue to the next step before the user responds.

    Next, ask the user a series of specific questions to clarify ambiguities in the natural language predicates and decision points. At this point, you should set the status to "asking_questions" using the set status tool.
    - Make sure your questions are simple, self-contained, and only address one issue at a time.
    - Do not assume that the user has read any of the transcripts; contextualize questions with sufficient detail.
    - Ask questions one by one as if you are having a conversation with a user. Do NOT put them all in the same message.
    - The user may have follow-up questions about specific details. Do your best to answer, and make your answers self-contained and comprehensive.

    Continue asking questions until the important principal components of uncertainty have been resolved. Once you feel like you have a pretty good idea of how would rewrite the rubric, do so using the set rubric tool while keeping the key components of a rubric in mind. Make sure that the rubric is sufficiently detailed and could be properly evaluated by another system.
</Procedure for engaging with the user>

<Formatting instructions>
    - Format your answers and rubrics in Markdown
    - To create a new line, use two newlines (\\n\\n)
    - Unordered lists (-), ordered lists (1.), bold (*), italics (_), code ticks (` or ```), and quotes (>) are supported
    - You may nest ordered and unordered lists, but make sure to use (1.) and (-) with the correct indentation
    - Headings are strictly forbidden. Do not use them
</Formatting instructions>
""".strip()
)

FIRST_USER_MESSAGE_TEMPLATE = """
<rubric>
{rubric}
</rubric>
<examples>
{examples}
</examples>
""".strip()


def create_set_status_tool() -> ToolInfo:
    return ToolInfo(
        name="set_status",
        description="Set the status of the refinement process",
        parameters=ToolParams(
            type="object",
            properties={
                "status": ToolParam(
                    name="status",
                    description="The status of the refinement process",
                    input_schema={
                        "type": "string",
                        "enum": [status.value for status in RefinementStatus],
                    },
                ),
            },
            required=["status"],
        ),
    )


def create_set_rubric_tool() -> ToolInfo:
    return ToolInfo(
        name="set_rubric",
        description="Set the Markdown text content of a rubric",
        parameters=ToolParams(
            type="object",
            properties={
                "text": ToolParam(
                    name="text",
                    description="The Markdown text content of the rubric",
                    input_schema={"type": "string"},
                ),
            },
            required=["text"],
        ),
    )


def execute_set_rubric(rubric: Rubric, tool_call: ToolCall):
    rubric.rubric_text = tool_call.arguments.get("text", "")
    rubric.version += 1
    return ToolMessage(
        content=str(rubric.version),  # The backend knows how to parse this
        tool_call_id=tool_call.id,
        function=tool_call.function,
        error=None,
    )


def execute_set_status(rsession: RefinementAgentSession, tool_call: ToolCall):
    status = cast(str, tool_call.arguments.get("status", RefinementStatus.DEFAULT_STATUS.value))
    rsession.status = RefinementStatus(status)
    return ToolMessage(
        content="Status set to " + status,
        tool_call_id=tool_call.id,
        function=tool_call.function,
        error=None,
    )
