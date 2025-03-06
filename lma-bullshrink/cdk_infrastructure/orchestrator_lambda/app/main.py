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


def prepare_lambda_inputs(
    call_id: str, transcription_bucket_uri: str, agenda_text: str
) -> list[ParallelFunctionCallConfig]:
    """
    Prepare input payloads for Lambda functions

    Args:
        call_id: The call ID
        transcription_bucket_uri: The S3 bucket URI
        agenda_text: The meeting agenda text
    Returns:
        Dict containing prepared inputs for each Lambda function
    """
    base_input = {
        "agenda_text": agenda_text,
        "transcription_path": f"{transcription_bucket_uri}/{call_id}-TRANSCRIPT.txt",
        "callId": call_id,
    }

    functions = [
        ParallelFunctionCallConfig(
            function_name=env_variables.scoring_lambda_name,
            input_event=base_input.copy(),
        )
    ]
    
    # Only run agenda alignment if agenda text is provided
    if agenda_text.strip():
        functions.append(
            ParallelFunctionCallConfig(
                function_name=env_variables.agenda_alignment_lambda_name,
                input_event=base_input.copy(),
            )
        )
    else:
        logger.info("No agenda text provided, skipping agenda alignment function")
        
    return functions


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
        event: Lambda event from LMA completion notification
        context: Lambda context
    Returns:
        Dict containing execution results
    """
    logger.info(f"Input event: {json.dumps(event)}")

    # Default agenda to use if none provided
    agenda_text = env_variables.default_agenda
    
    # Handle S3 trigger events from LMA
    if event.get("Records") and event["Records"][0].get("eventSource") == "aws:s3":
        s3_event = event["Records"][0]["s3"]
        bucket_name = s3_event["bucket"]["name"]
        object_key = s3_event["object"]["key"]
        
        # Extract call_id from object key (assuming format like "callId-TRANSCRIPT.txt")
        call_id = object_key.split("-TRANSCRIPT.txt")[0]
        
        # Download and parse the summary file if available
        s3_client = boto3.client("s3")
        try:
            summary_key = f"{call_id}-SUMMARY.txt"
            summary_response = s3_client.get_object(Bucket=bucket_name, Key=summary_key)
            meeting_summary_text = summary_response["Body"].read().decode("utf-8")
            try:
                meeting_summary = json.loads(meeting_summary_text).get(
                    "SUMMARY", "Could not parse the meeting summary."
                )
            except json.JSONDecodeError:
                meeting_summary = meeting_summary_text
        except Exception as e:
            logger.warning(f"Could not retrieve summary for {call_id}: {str(e)}")
            meeting_summary = "No summary available"
            
        # Check if there's an agenda file available
        try:
            agenda_key = f"{call_id}-AGENDA.txt"
            agenda_response = s3_client.get_object(Bucket=bucket_name, Key=agenda_key)
            agenda_text = agenda_response["Body"].read().decode("utf-8")
            logger.info(f"Retrieved agenda from S3: {agenda_text}")
        except Exception as e:
            logger.warning(f"Could not retrieve agenda file for {call_id}: {str(e)}")
            # Keep the default agenda
    
    # Handle direct invocation with CallId and CallSummaryText
    else:
        try:
            input_event = InputEvent(**event)
            call_id = sanitize_key_prefix(raw_call_id=input_event.CallId)
            meeting_summary = json.loads(input_event.CallSummaryText).get(
                "SUMMARY", "Could not parse the meeting summary."
            )
            bucket_name = env_variables.call_transcripts_bucket_name
            
            # Check if agenda is provided in the input event
            if input_event.AgendaText:
                agenda_text = input_event.AgendaText
                logger.info(f"Using agenda from input event: {agenda_text}")
        except Exception as e:
            logger.error(f"Error parsing direct invocation event: {str(e)}")
            return {
                "statusCode": 400,
                "body": {"message": f"Invalid input event format: {str(e)}"},
            }

    call_transcripts_bucket_uri = f"s3://{bucket_name}"
    logger.info(f"Meeting (ID: {call_id}) summary: {meeting_summary}")

    parallel_function_call_configs = prepare_lambda_inputs(
        call_id=call_id,
        transcription_bucket_uri=call_transcripts_bucket_uri,
        agenda_text=agenda_text,
    )

    # Convert to the format expected by invoke_functions_parallel
    function_calls = {
        config.function_name: config.input_event 
        for config in parallel_function_call_configs
    }

    # Execute functions in parallel
    responses = invoke_functions_parallel(function_calls)

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

    # Add meeting summary to responses for email
    responses["meeting_summary"] = meeting_summary

    # Invoke email fanout Lambda
    lambda_client = boto3.client("lambda")
    email_response = lambda_client.invoke(
        FunctionName=env_variables.email_fanout_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(responses),
    )

    response_payload = json.loads(email_response["Payload"].read().decode("utf-8"))
    responses[env_variables.email_fanout_lambda_name] = response_payload

    return {
        "statusCode": 200,
        "body": {"message": "Functions executed successfully", "results": responses},
    }
