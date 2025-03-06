import json
import os
import logging
import boto3
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def create_html_content(data):
    try:
        # Extract relevant data
        meeting_summary = data.get("meeting_summary", "No summary available")
        
        # Find agenda alignment data
        agenda_alignment_key = None
        for key in data:
            if key.endswith("AgendaAlignmentFunction"):
                agenda_alignment_key = key
                break
        
        # Find scoring data
        scoring_key = None
        for key in data:
            if key.endswith("ScoringFunction"):
                scoring_key = key
                break
        
        if not scoring_key:
            logger.warning("Missing scoring function response in data")
            scores_data = {"overall_scores": []}
            
        if not agenda_alignment_key:
            logger.warning("Agenda alignment function response not found, likely because no agenda was provided")
            agenda_alignment = {
                "overall": "No agenda was provided for this meeting, so agenda alignment could not be evaluated.",
                "participants": []
            }
        
        else:
            # Extract data from function responses
            agenda_alignment = data[agenda_alignment_key].get("body", {}).get("body", {}).get("agenda_alignment", {})
            scores_data = data[scoring_key].get("body", {})
        
        # Calculate overall meeting score (average of on-point scores if available)
        overall_scores = scores_data.get("overall_scores", [])
        if overall_scores:
            avg_meeting_score = sum(p.get("overall_on_point_score", 0) for p in overall_scores) / len(overall_scores)
        else:
            avg_meeting_score = 0

        # Create HTML content
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .section {{ margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 5px; }}
                .header {{ color: #2c3e50; font-size: 24px; margin-bottom: 20px; }}
                .subheader {{ color: #34495e; font-size: 18px; margin: 15px 0; }}
                .score {{ color: {'#27ae60' if avg_meeting_score >= 70 else '#e74c3c'}; font-weight: bold; }}
                table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">Meeting Analysis Report</div>
            
            <div class="section">
                <div class="subheader">Meeting Summary</div>
                <p>{meeting_summary}</p>
            </div>

            <div class="section">
                <div class="subheader">Overall Meeting Score: <span class="score">{avg_meeting_score:.1f}%</span></div>
                <p>{agenda_alignment.get('overall', 'No alignment data available')}</p>
            </div>
        """

        # Add participant scores if available
        if overall_scores:
            html += """
            <div class="section">
                <div class="subheader">Participant Scores</div>
                <table>
                    <tr>
                        <th>Participant</th>
                        <th>On-Point Score</th>
                        <th>Bullshit Score</th>
                        <th>Eloquence Score</th>
                    </tr>
            """

            # Add participant scores
            for score in overall_scores:
                html += f"""
                    <tr>
                        <td>{score.get('person', 'Unknown')}</td>
                        <td>{score.get('overall_on_point_score', 'N/A')}%</td>
                        <td>{score.get('overall_bullshit_score', 'N/A')}%</td>
                        <td>{score.get('overall_eloquence_score', 'N/A')}%</td>
                    </tr>
                """
            
            html += "</table></div>"
        
        # Add participant feedback from agenda alignment if available
        participants = agenda_alignment.get("participants", [])
        if participants:
            html += """
            <div class="section">
                <div class="subheader">Participant Agenda Adherence</div>
                <ul>
            """
            
            for participant in participants:
                html += f"""
                <li><strong>{participant.get('name', 'Unknown')}</strong>: {participant.get('feedback', 'No feedback available')}</li>
                """
            
            html += "</ul></div>"

        # Add suggestions for better meetings
        html += """
            <div class="section">
                <div class="subheader">How to Schedule Better Meetings</div>
                <ul>
                    <li>Set clear agenda items and time limits for each topic</li>
                    <li>Share meeting materials in advance</li>
                    <li>Keep discussions focused and on-topic</li>
                    <li>Encourage active participation from all attendees</li>
                    <li>Document action items and follow-up tasks</li>
                    <li>Start and end meetings on time</li>
                </ul>
            </div>
        </body>
        </html>
        """

        return html
        
    except Exception as e:
        logger.error(f"Error creating HTML content: {str(e)}")
        # Return a simple error HTML page
        return f"""
        <html>
        <body>
            <h1>Meeting Analysis Report</h1>
            <p>There was an error generating the report: {str(e)}</p>
            <p>Meeting summary: {data.get('meeting_summary', 'Not available')}</p>
        </body>
        </html>
        """


def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    
    # SES client setup
    ses = boto3.client("ses", region_name="us-east-1")  # Change region as needed

    # Email parameters - get from environment or fallback to defaults
    SENDER = os.environ.get("SENDER_EMAIL", "bullshrink@example.com")
    RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "admin@example.com")
    SUBJECT = "BullShrink Meeting Analysis Report"

    # Create message container
    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"] = SENDER
    msg["To"] = RECIPIENT

    try:
        # Create HTML content
        html_content = create_html_content(event)

        # Attach HTML content
        part = MIMEText(html_content, "html")
        msg.attach(part)

        # Send the email
        response = ses.send_raw_email(
            Source=SENDER,
            Destinations=[RECIPIENT],
            RawMessage={"Data": msg.as_string()},
        )
        logger.info(f"Email sent successfully: {json.dumps(response)}")
        return {"statusCode": 200, "body": json.dumps("Email sent successfully!")}
        
    except ClientError as e:
        logger.error(f"Error sending email with SES: {str(e)}")
        return {"statusCode": 500, "body": json.dumps(f"Error sending email: {str(e)}")}
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps(f"Unexpected error: {str(e)}")}
