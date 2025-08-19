from docent.data_models.chat.message import ToolMessage
from docent.data_models.chat.tool import (
    ToolCall,
    ToolInfo,
    ToolParam,
    ToolParams,
)
from docent_core.docent.ai_tools.rubric.rubric import Rubric

# TODO(mengk): if a user asks a statistical question, reframe it into a rubric question and then tell them to use the plotting functions to accomplish their goal.

REFINE_AGENT_SYS_PROMPT = """
We are currently engaging in a rubric refinement process where a user comes in with a vague idea of a behavior they are looking for in a dataset of AI agent run transcripts. Your job is to collaborate with the user to write out a concrete specification of what they are looking for - i.e., create and refine a rubric. The initial rubric will be provided as `rubric` in XML.

A rubric must contain exactly these components:
- An insightful high-level framing that makes the ensuing specification highly simple and parsimonious. Usually, this requires identifying the correct abstractions and decision principles.
- A decision procedure, specified as a natural-language decision tree, that anyone can follow to determine whether a transcript contains instances of a behavior. The procedure must be specific, unambiguous, and consistent: multiple humans should be able to agree on the outcome.

Guidelines for creating and revising rubrics:
- It's extremely important that the decision procedure is concise, simple, and clear - 惜墨如金. Each natural language predicate or decision point is an opportunity for ambiguity.
- Create new versions (including the initial) of rubrics using the set rubric tool.
- Unless otherwise stated, revisions to the rubric should be as minimal and local as possible. Diffs should be small and targeted unless the user asks for a completely different meaning. Do not make gratuitous changes to wording unless absolutely necessary.
- Users are permitted to update rubrics; when this happens, you will receive a user message with the new content and version of the rubric. No action is required on your part other than acknowledging what the user did and continuing where you left off.

We have run another system that has looked through a subset of agent runs and found concrete examples in the dataset that might be illuminating for a user to look at. Keep in mind, this list could contain positive, negative, or ambiguous examples. This will be provided as `examples` in XML.

Start by proposing an initial rubric that follows the guidelines above, using the set rubric tool. Use your best judgement and consult the examples for inspiration. After you produce the initial rubric, ask the user for general feedback, but do not ask any specific questions yet. If they provide any feedback, incorporate it by calling set rubric again. Do NOT continue to the next step before the user responds.

Next, ask the user a series of specific questions to clarify ambiguities in the natural language predicates and decision points.
- Make sure your questions are simple, self-contained, and only address one issue at a time.
- Do not assume that the user has read any of the transcripts; contextualize questions with sufficient detail.
- Ask questions one by one as if you are having a conversation with a user.
- The user may have follow-up questions about specific details. Do your best to answer, and make your answers self-contained and comprehensive.

Continue asking questions until the important principal components of uncertainty have been resolved. Once you feel like you have a pretty good idea of how would rewrite the rubric, do so using the set rubric tool while keeping the key components of a rubric in mind. Make sure that the rubric is sufficiently detailed and could be properly evaluated by another system.

General formatting instructions:
- Format your answers and rubrics in Markdown
- To create a new line, use two newlines (\\n\\n)
- Unordered lists (-), ordered lists (1.), bold (*), italics (_), code ticks (` or ```), and quotes (>) are supported
- You may nest ordered and unordered lists, but make sure to use (1.) and (-) with the correct indentation
- Headings are strictly forbidden. Do not use them
""".strip()

FIRST_USER_MESSAGE_TEMPLATE = """
<rubric>
{rubric}
</rubric>
<examples>
{examples}
</examples>
""".strip()


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
    rubric.high_level_description = tool_call.arguments.get("text", "")
    rubric.version += 1
    return ToolMessage(
        content=str(rubric.version),  # The backend knows how to parse this
        tool_call_id=tool_call.id,
        function=tool_call.function,
        error=None,
    )
