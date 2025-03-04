import json
import boto3
import logging
import re

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


def extract_topics(text):
    # Extract the "DETAILS" section
    topics_start = text.find("**Key Topics**")
    topics_end = text.find('"ACTIONS":')
    topics_text = text[topics_start:topics_end]

    # Extract individual topics using regex
    topics = re.findall(r"- (.*)", topics_text, re.MULTILINE)

    # Output the topics as a plain text list
    agenda = ""
    for topic in topics:
        agenda += f"\n- {topic}"

    return agenda


def create_user_prompt(agenda, transcription):
    """
    Create a user prompt for evaluating on-point scores based on the provided agenda and transcription.

    Parameters:
    agenda (str): The meeting agenda as a string.
    transcription (str): The meeting transcription as a string.

    Returns:
    str: The user prompt for the LLM.
    """

    user_prompt = f"""
Based on the provided agenda and transcription of the meeting, please calculate the on-point score, bullshit score, eloquence score, and unprofessionality score for each person for each topic in the agenda. The scores range from 0 to 100. 

- **On-point score**: Higher scores indicate better communication regarding the topic.
- **Bullshit score**: Higher scores indicate worse communication.
- **Eloquence score**: Higher scores indicate more eloquent speech.
- **Unprofessionality score**: Higher scores indicate more unprofessional behavior.

Transcription:
{transcription}

Agenda:
{agenda}

Please calculate the contribution of each factor to the final score for each person for each topic. The percentages should sum up to 100% depending on the contribution to the scores.

Provide the scores in the following format:
{{
  "agenda_topics": [
    {{
      "topic": "[Agenda Item]",
      "evaluations": [
        {{
          "person": "[Name]",
          "on_point_score": [Score],
          "bullshit_score": [Score],
          "eloquence_score": [Score],
          "unprofessionality_score": [Score],
          "contribution_factors": {{
            "talking_about_non_related_things": [Percentage],
            "talking_generically": [Percentage],
            "talking_on_point": [Percentage],
            "proposing_solutions": [Percentage],
            "enough_depth": [Percentage],
            "unprofessional_behavior": [Percentage]
          }},
          "justification": "[Justification for the score]"
        }}
        // ... more evaluations
      ]
    }}
    // ... more topics
  ],
  "overall_scores": [
    {{
      "person": "[Name]",
      "overall_on_point_score": [Score],
      "overall_bullshit_score": [Score],
      "overall_eloquence_score": [Score],
      "overall_unprofessionality_score": [Score],
      "contribution_factors": {{
        "talking_about_non_related_things": [Percentage],
        "talking_generically": [Percentage],
        "talking_on_point": [Percentage],
        "proposing_solutions": [Percentage],
        "enough_depth": [Percentage],
        "unprofessional_behavior": [Percentage]
      }},
      "justification": "[Justification for the score]"
    }}
    // ... more overall scores
  ]
}}

You have to provide only plain json output, without any pre and post text including ```json and ``` 
"""

    return user_prompt


system_message = """
You are an LLM designed to analyze meeting transcriptions and evaluate how on-point, bullshit, profanity, eloquence, and unprofessionality scores each participant's speech is regarding the meeting agenda. 

To calculate the score:
1. Identify the topics in the agenda.
2. For each topic, assess whether the participant's speech is related to the topic.
3. Penalize the score if the participant talks about non-related things.
4. Reward the score if the participant talks about related things concisely and accurately.
5. Evaluate the eloquence of the speech and reward the eloquence score accordingly.
6. Assess any unprofessional behavior and penalize the unprofessionality score accordingly.
7. Ensure the final score reflects the participant's overall relevance, conciseness, professionalism, and eloquence in their speech.
8. Provide a justification for each score.

Use the provided transcription to evaluate each participant's speech for each topic.

PLease use below guidance for detecting bullshit

1. Context and Background:

    Gather information about the topic of discussion.
    Understand the context in which the conversation is taking place.

2. Language and Tone:

    Vagueness: Look for statements that are overly vague or lack specific details.
        Example: "It’s really effective, trust me."
    Overconfidence: Note any expressions of extreme confidence without substantial evidence.
        Example: "This is absolutely the best way to do it."
    Jargon Overload: Be cautious of excessive use of technical terms or jargon that seems designed to impress rather than inform.
        Example: "Utilizing synergistic paradigms will optimize our operational efficacy."

3. Consistency:

    Contradictions: Identify any contradictions within the person’s statements or between their statements and known facts.
        Example: "I’ve been in this industry for 20 years, but I just started last month."
    Changing Stories: Watch for changes in the narrative over time.
        Example: Different explanations for the same event in separate conversations.

4. Evidence and Sources:

    Lack of Evidence: Question claims that are not supported by data, examples, or credible sources.
        Example: "This method guarantees success, but I can’t show you any results."
    Cherry-Picking: Be wary of selective use of data or examples that support only one side of an argument.
        Example: Citing a single success story without acknowledging failures.

5. Emotional Appeals:

    Appeal to Emotion: Identify attempts to elicit emotional responses rather than logical reasoning.
        Example: "You have to believe me, it’s for the greater good."
    Ad Hominem Attacks: Look for personal attacks instead of addressing the argument.
        Example: "You wouldn’t understand, you’re not smart enough."

6. Red Flags:

    Pressure Tactics: Be aware of attempts to rush decisions or create a sense of urgency without valid reason.
        Example: "You need to decide now, or you’ll miss out on this incredible opportunity."
    Secretive Behavior: Notice any reluctance to share information or provide transparency.
        Example: "I can’t tell you the details, but trust me, it’s good."

7. Follow-Up Questions:

    Ask for clarification and more information to test the validity of claims.
        Example: "Can you provide more details on how this works?" or "What evidence do you have to support that claim?"

Conclusion:

    Use these indicators to form a balanced judgment. No single sign definitively means someone is "talking bullshit," but a combination of these factors can raise red flags.

"""


class Bedrock:
    def __init__(self, model_id):
        self.client_br = boto3.client("bedrock-runtime")
        self.model_id = model_id

    def call_nova(
        self,
        model,
        messages,
        max_tokens=5000,
        temp=0.5,
        top_p=0.99,
        top_k=20,
        verbose=False,
    ):
        system_list = [{"text": system_message}]
        inf_params = {
            "max_new_tokens": max_tokens,
            "top_p": top_p,
            "top_k": top_k,
            "temperature": temp,
        }
        request_body = {
            "messages": messages,
            "system": system_list,
            "inferenceConfig": inf_params,
        }
        if verbose:
            print("Request Body", request_body)
        response = self.client_br.invoke_model(
            modelId=model, body=json.dumps(request_body)
        )
        model_response = json.loads(response["body"].read())
        return model_response, model_response["output"]["message"]["content"][0]["text"]

    def answer_question(self, question):
        messages = [{"role": "user", "content": [{"text": question}]}]
        model_response, answer = self.call_nova(self.model_id, messages)

        return answer


def lambda_handler(event, context):
    model_id = "amazon.nova-lite-v1:0"
    print(f"model: {model_id}")
    print(f"event: {event}")

    bedrock = Bedrock(model_id)

    # # Validate input
    # if "agenda_path" not in event or "transcription_path" not in event:
    #     raise ValueError(
    #         "Missing required fields: 'agenda_path' and/or 'transcription_path'"
    #     ) # This is not how you validate events :D

    eventId = event["eventId"]

    # Parse S3 paths
    transcription_bucket, transcription_key = parse_s3_path(event["transcription_path"])

    # K: Dirty hack around the agenda limitations
    agenda_path = event.get("agenda_path")
    if agenda_path:
        agenda_bucket, agenda_key = parse_s3_path(agenda_path)
    try:
        agenda_text = get_s3_content(agenda_bucket, agenda_key)
    except Exception as e:
        agenda_text = ""
    agenda_text = (
        extract_topics(agenda_text)
        if agenda_text
        else event.get(
            "hardcoded_agenda_text",
            "Unfortunately, no agenda was provided, please try to extract it from the beginning of the transcript (someone must have mentioned the agenda).",
        )
    )

    logger.info(f"Extracted agenda topics: {agenda_text}")
    transcription_text = get_s3_content(transcription_bucket, transcription_key)

    user_prompt = create_user_prompt(agenda_text, transcription_text)
    answer = bedrock.answer_question(user_prompt)
    logger.info(f"Model response: {answer}")

    json_answer = json.loads(answer)  # eval(answer)  # BIG security oof
    return {"statusCode": 200, "body": json_answer}
