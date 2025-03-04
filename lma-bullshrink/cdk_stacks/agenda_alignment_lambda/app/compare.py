import json
import traceback

import boto3
from botocore.exceptions import ClientError

bedrock_runtime = boto3.client("bedrock-runtime")


def create_prompt_template(template_type="general", **kwargs):
    """
    Create a prompt template based on the specified type and parameters

    Parameters:
        template_type (str): Type of template to create
        **kwargs: Additional parameters specific to the template type

    Returns:
        str: Formatted prompt template
    """
    templates = {
        "general": """
            Please provide a response to the following:
            {input_text}
        """,
        "summarize": """
            Please provide a concise summary of the following text:
            {input_text}
            
            Key points to address:
            - Main ideas
            - Important details
            - Key conclusions
        """,
        "agenda_vs_meeting": """
            Please compare the agenda with the actual meeting transcript and provide feedback. Provide details how each pearson was sticking to the agenda. Provide overall feedback as well.

            {response}
    
            Provide your analysis in the exact JSON format specified above.

            Agenda:
            {agenda}

            Meeting Transcript:
            {input_text}
        """,
        "analyze": """
            Please analyze the following text and provide insights:
            {input_text}
            
            Consider these aspects:
            - Key themes
            - Main arguments
            - Supporting evidence
            - Potential implications
        """,
        "extract_info": """
            From the following text, please extract:
            - Names: {entities_to_extract}
            - Dates: Any mentioned dates or time periods
            - Key facts: Important numerical or factual information
            
            Text to analyze:
            {input_text}
        """,
        "code_review": """
            Please review the following code and provide feedback:
            
            ```{language}
            {input_text}
            ```
            
            Consider:
            1. Code quality and best practices
            2. Potential bugs or issues
            3. Performance considerations
            4. Security concerns
            5. Suggested improvements
        """,
        "custom": "{input_text}",
    }

    try:
        # Get the base template
        base_template = templates.get(template_type, templates["general"])

        # Format the template with provided parameters
        formatted_template = base_template.format(**kwargs)

        # Clean up the template (remove extra whitespace and normalize line endings)
        formatted_template = "\n".join(
            line.strip() for line in formatted_template.splitlines()
        )

        return formatted_template

    except KeyError as e:
        raise ValueError(
            f"Template type '{template_type}' not found: {str(traceback.format_exc())}"
        )
    except Exception as e:
        raise Exception(f"Error creating template: {str(e)}")


def invoke_bedrock_model(
    input_text, bedrock_runtime, model_id="anthropic.claude-3-haiku-20240307-v1:0"
):
    """
    Send text to Amazon Bedrock model and get the response

    Parameters:
        input_text (str): The text to send to the model
        model_id (str): The model ID to use

    Returns:
        str: The model's response text
    """
    try:
        # Format the request based on the model type
        if "anthropic.claude" in model_id:
            # Claude-specific request format
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "temperature": 0.7,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": input_text}]}
                ],
            }
        elif "amazon.titan" in model_id:
            # Titan-specific request format
            request_body = {
                "inputText": input_text,
                "textGenerationConfig": {
                    "maxTokenCount": 512,
                    "temperature": 0.7,
                },
            }
        else:
            raise ValueError(f"Unsupported model ID: {model_id}")

        # Invoke the model
        response = bedrock_runtime.invoke_model(
            modelId=model_id, body=json.dumps(request_body)
        )

        # Parse the response
        response_body = json.loads(response.get("body").read())

        # Extract the response text based on the model type
        if "anthropic.claude" in model_id:
            response_text = response_body.get("content")[0].get("text")
        elif "amazon.titan" in model_id:
            response_text = response_body.get("results")[0].get("outputText")

        return response_text

    except ClientError as e:
        print(f"Error invoking Bedrock model: {str(e)}")
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise


def compare_agenda_vs_meeting(
    agenda, transcription, model_id="anthropic.claude-3-haiku-20240307-v1:0"
):
    """
    Combines prompt template creation with Bedrock invocation

    Parameters:
        input_str (str): The formatted prompt text
        model_id (str): The Bedrock model ID to use

    Returns:
        str: Model response
    """
    try:
        response = """
					{
       			"agenda_alignment": {
							"participants: [
								{
									"name": "string",
									"feedback": "string"
								}
							],
							"overall": "string"
						}
     			}
    		"""
        prompt_text = create_prompt_template(
            template_type="agenda_vs_meeting",
            input_text=transcription,
            agenda=agenda,
            response=response,
        )
        return invoke_bedrock_model(prompt_text, bedrock_runtime, model_id)

    except Exception as e:
        raise Exception(f"Error sending prompt to Bedrock: {str(e)}")
