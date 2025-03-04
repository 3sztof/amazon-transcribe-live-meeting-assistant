import concurrent.futures
import json
import logging
import time
from typing import Any, Dict

import boto3
from botocore.config import Config
from data_models import OrchestratorLambdaEnv, ParallelFunctionCallConfig, InputEvent
from utils import sanitize_key_prefix

logger = logging.getLogger()
logger.setLevel(logging.INFO)

lambda_client_config = Config(retries=dict(max_attempts=3, mode="adaptive"))
lambda_client = boto3.client("lambda", config=lambda_client_config)


env_variables = OrchestratorLambdaEnv()

AGENDA_TEXT = """
Agenda:
1. Sprint  Progress Update (3 mins)
2. Technical  Blockers Discussion (5 mins)
3. Upcoming  Release Planning (5 mins)
4. AOB  - Any Other Business (2 mins)
""".strip()  # TODO(feature): figure out how to determine meeting agenda / pull it from LMA


def prepare_lambda_inputs(
    call_id: str, transcription_bucket_uri: str
) -> list[ParallelFunctionCallConfig]:
    """
    Prepare input payloads for Lambda functions

    Args:
        call_id: The call ID
        transcription_bucket_uri: The S3 bucket URI
    Returns:
        Dict containing prepared inputs for each Lambda function
    """
    base_input = {
        "agenda_text": AGENDA_TEXT,
        "transcription_path": f"{transcription_bucket_uri}/{call_id}-TRANSCRIPT.txt",
        "callId": call_id,
    }

    return [
        ParallelFunctionCallConfig(
            function_name=env_variables.scoring_lambda_name,
            input_event=base_input.copy(),
        ),
        ParallelFunctionCallConfig(
            function_name=env_variables.agenda_alignment_lambda_name,
            input_event=base_input.copy(),
        ),
    ]


def handle_lambda_invocation(function_name: str, input_event: Dict) -> Dict:
    """
    Handle the invocation of a single Lambda function

    Args:
        function_name: Name of the Lambda function to invoke
        input_event: Input payload for the function
    Returns:
        Dict containing the response or error information
    """
    try:
        logger.info(f"Invoking function: {function_name} with input: {input_event}")

        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(input_event),
        )

        response_payload = json.loads(response["Payload"].read().decode("utf-8"))

        logger.info(f"Response from {function_name}: {json.dumps(response_payload)}")

        return {"statusCode": response.get("StatusCode"), "body": response_payload}
    except Exception as e:
        logger.error(f"Error invoking {function_name}: {str(e)}")
        return {"error": str(e)}


def invoke_functions_parallel(function_calls: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Invoke multiple Lambda functions in parallel

    Args:
        function_calls: Dictionary of function names and their input payloads
    Returns:
        Dict containing responses from all functions
    """
    responses = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_function = {
            executor.submit(handle_lambda_invocation, name, input_event): name
            for name, input_event in function_calls.items()
        }
        for future in concurrent.futures.as_completed(future_to_function):
            function_name = future_to_function[future]
            responses[function_name] = future.result()
    return responses


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler function

    Args:
        event: Lambda event
        context: Lambda context
    Returns:
        Dict containing execution results
    """
    logger.info(f"Input event: {json.dumps(event)}")

    input_event = InputEvent(**event)

    call_transcripts_bucket_uri = f"s3://{env_variables.call_transcripts_bucket_name}"

    call_id = sanitize_key_prefix(raw_call_id=input_event.CallId)
    meeting_summary = json.loads(input_event.CallSummaryText).get(
        "SUMMARY", "Could not parse the meeting summary."
    )
    # TODO(feature): pull action points from LMA, put them in the meeting report email

    logger.info(f"Meeting (ID: {call_id}) summary: {meeting_summary}")

    parallel_function_call_inputs = prepare_lambda_inputs(
        call_id=call_id,
        transcription_bucket_uri=call_transcripts_bucket_uri,
    )

    time.sleep(30)

    # Execute functions in parallel
    responses = invoke_functions_parallel(parallel_function_call_inputs)

    # Check for any failed invocations
    errors = {name: resp for name, resp in responses.items() if "error" in resp}
    if errors:
        logger.error(f"Some functions failed: {json.dumps(errors)}")
        return {
            "statusCode": 207,  # Partial success
            "body": {"message": "Some functions failed", "results": responses},
        }

    logger.info("All functions completed successfully")
    logger.info(f"Responses: {json.dumps(responses)}")

    # Email
    responses["meeting_summary"] = meeting_summary

    lambda_client = boto3.client("lambda")

    # Invoke the Lambda function
    email_response = lambda_client.invoke(
        FunctionName=EMAIL_FANOUT_LAMBDA,
        InvocationType="RequestResponse",
        Payload=json.dumps(responses),
    )

    responses[EMAIL_FANOUT_LAMBDA] = email_response.get("body")

    return {
        "statusCode": 200,
        "body": {"message": "Functions executed successfully", "results": responses},
    }
