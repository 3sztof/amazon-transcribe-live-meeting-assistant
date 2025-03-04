from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings


class OrchestratorLambdaEnv(BaseSettings):
    call_transcripts_bucket_name: str = Field(default=...)
    scoring_lambda_name: str = Field(default=...)
    agenda_alignment_lambda_name: str = Field(default=...)
    email_fanout_lambda_name: str = Field(default=...)

    class Config:
        extra = "ignore"


class ParallelFunctionCallConfig(BaseModel):
    function_name: str
    input_event: dict


class InputEvent(BaseModel):
    CallId: str
    CallSummaryText: str
