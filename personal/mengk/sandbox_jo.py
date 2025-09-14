from typing import Any

from pydantic import BaseModel


class Judge(BaseModel):
    id: str
    prompt: str
    model: str
    output_json_schema: dict[str, Any]
    sampling_params: dict[str, Any]


class JudgeRun(BaseModel):
    id: str
    judge_id: str
    agent_run_id: str
    fmt_args: dict[str, Any]


class JudgeResult(BaseModel):
    id: str
    judge_id: str  # technically derivable from judge_run_id
    judge_run_id: str
    value: dict[str, Any]  # conforms to judge's output_json_schema


class FormatArgs(BaseModel):
    version: str  # so we can maintain backwards compatibility


class FormatArgsV1(FormatArgs):
    version: str = "v1"

    # Specifically for this version, we ask for these fields:


class AgentRun(BaseModel):
    # whatever data args

    def text(self, fmt_args: dict[str, Any]):
        return "..."
