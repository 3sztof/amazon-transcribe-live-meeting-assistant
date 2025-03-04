import json
import logging
from typing import Dict, Any

import boto3

from compare import compare_agenda_vs_meeting

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_s3_content(bucket: str, key: str) -> str:
    """
    Retrieve content from S3 file

    Parameters:
        bucket (str): S3 bucket name
        key (str): S3 object key

    Returns:
        str: Content of the S3 file
    """
    try:
        s3_client = boto3.client("s3")
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8")
        return content
    except Exception as e:
        logger.error(f"Error reading from S3 - Bucket: {bucket}, Key: {key}: {str(e)}")
        raise


def parse_s3_path(s3_path: str) -> tuple:
    """
    Parse S3 path into bucket and key

    Parameters:
        s3_path (str): S3 path in format 's3://bucket-name/key/path'

    Returns:
        tuple: (bucket_name, key)
    """
    try:
        path = s3_path.replace("s3://", "")
        bucket = path.split("/")[0]
        key = "/".join(path.split("/")[1:])
        return bucket, key
    except Exception as e:
        logger.error(f"Error parsing S3 path {s3_path}: {str(e)}")
        raise


def get_meeting_agenda_quality(
    agenda_text: str, transcription_text: str
) -> Dict[str, Any]:
    """
    Compare agenda with meeting transcription

    Parameters:
        agenda_text (str): The agenda text content
        transcription_text (str): The transcription text content

    Returns:
        Dict[str, Any]: Comparison results
    """
    try:
        # Import your actual comparison logic here

        result = compare_agenda_vs_meeting(agenda_text, transcription_text)
        return result
    except Exception as e:
        logger.error(f"Error in comparison: {str(e)}")
        raise


def lambda_handler(event, context):
    """
    Lambda handler to process agenda and transcription comparison

    Parameters:
        event (dict): Must contain 'agenda_path' and 'transcription_path'
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: Comparison results with status code
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # # Validate input
    # if 'agenda_path' not in event or 'transcription_path' not in event:
    #     raise ValueError("Missing required fields: 'agenda_path' and/or 'transcription_path'") # Guys, whyyy?

    # Parse S3 paths
    transcription_bucket, transcription_key = parse_s3_path(event["transcription_path"])

    # Get contents from S3
    transcription_text = get_s3_content(transcription_bucket, transcription_key)

    # K: Dirty hack around the agenda limitations
    agenda_path = event.get("agenda_path")
    if agenda_path:
        agenda_bucket, agenda_key = parse_s3_path(agenda_path)
    try:
        agenda_text = get_s3_content(agenda_bucket, agenda_key)
    except Exception as e:
        agenda_text = ""
    agenda_text = (
        agenda_text
        if agenda_text
        else event.get(
            "hardcoded_agenda_text",
            "Unfortunately, no agenda was provided, please try to extract it from the beginning of the transcript (someone must have mentioned the agenda).",
        )
    )

    # Perform comparison
    comparison_result = get_meeting_agenda_quality(agenda_text, transcription_text)

    # Sanitize the result by checking if it is a JSON
    try:
        result = json.loads(comparison_result)
    except:
        raise ValueError("Comparison result is not a valid JSON")

    # Prepare successful response
    response = {
        "statusCode": 200,
        "body": result,
    }

    logger.info(f"Comparison completed successfully: {json.dumps(response)}")
    return response
