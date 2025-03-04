from aws_cdk import (
    Stack,
    aws_lambda,
    aws_s3,
    CfnParameter,
    Duration,
)
from constructs import Construct
from aws_cdk.aws_lambda_python_alpha import PythonLayerVersion, PythonFunction


class BullShrinkAppStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope=scope, id=construct_id, **kwargs)

        python_runtime = aws_lambda.Runtime.PYTHON_3_12

        # Call transcripts location
        call_transcripts_bucket_name = CfnParameter(
            scope=self,
            id="CallTranscriptsBucketName",
            description="Name of the S3 bucket containing call transcripts",
            type="String",
        ).value_as_string
        call_transcript_bucket = aws_s3.Bucket.from_bucket_name(
            scope=self,
            id="CallTranscriptBucket",
            bucket_name=call_transcripts_bucket_name,
        )

        # BullShrink scoring
        scoring_function = PythonFunction(
            scope=self,
            id="ScoringFunction",
            entry="scoring_lambda/",
            runtime=python_runtime,
            handler="app.main.lambda_handler",
            index="handler.py",
            timeout=Duration.minutes(amount=5),
            memory_size=128,
            environment={
                "CALL_TRANSCRIPTS_BUCKET_NAME": call_transcripts_bucket_name,
            },
        )

        call_transcript_bucket.grant_read(scoring_function)

        # Agenda alignment
        agenda_alignment_function = PythonFunction(
            scope=self,
            id="AgendaAlignmentFunction",
            entry="agenda_alignment_lambda/",
            runtime=python_runtime,
            handler="app.main.lambda_handler",
            index="handler.py",
            timeout=Duration.minutes(amount=5),
            memory_size=128,
            environment={},
        )

        email_fanout_function = PythonFunction(
            scope=self,
            id="EmailFanoutFunction",
            entry="email_fanout_lambda/",
            runtime=python_runtime,
            handler="app.main.lambda_handler",
            index="handler.py",
            timeout=Duration.minutes(amount=5),
            memory_size=128,
            layers=[
                PythonLayerVersion(
                    scope=self,
                    id="EmailFanoutFunctionLayer",
                    entry="email_fanout_lambda/",
                    compatible_runtimes=[python_runtime],
                    description="Email fanout function layer",
                )
            ],
            environment={},
        )

        # Orchestration
        self.orchestrator_function = PythonFunction(
            scope=self,
            id="OrchestratorFunction",
            entry="orchestrator_lambda/",
            runtime=python_runtime,
            handler="app.main.lambda_handler",
            index="handler.py",
            timeout=Duration.minutes(amount=5),
            memory_size=128,
            environment={
                "CALL_TRANSCRIPTS_BUCKET_NAME": call_transcripts_bucket_name,
                "SCORING_LAMBDA_NAME": scoring_function.function_name,
                "AGENDA_ALIGNMENT_LAMBDA_NAME": agenda_alignment_function.function_name,
                "EMAIL_FANOUT_LAMBDA_NAME": email_fanout_function.function_name,
            },
        )

        orchestrated_functions: list[PythonFunction] = [
            scoring_function,
            agenda_alignment_function,
            email_fanout_function,
        ]
        for function in orchestrated_functions:
            function.grant_invoke(grantee=self.orchestrator_function)
