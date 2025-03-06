# LMA BullShrink

> **⚠️ WORK IN PROGRESS: This module's integration with the LMA core is not yet fully implemented. Proper interfaces and integration points are still being developed.**

> **Note: BullShrink is a joke module created during a hackathon event. It is intended to be humorous and should not be used for serious evaluation of actual meetings or participants.**

BullShrink is a fun, satirical extension module for Amazon Transcribe Live Meeting Assistant (LMA) that analyzes meeting transcripts to provide tongue-in-cheek "insights" about meeting effectiveness, participant contribution, and agenda adherence.

## Entertaining "Features"

- **Satirical Meeting Scoring**: Humorously analyzes each participant's contribution with clearly tongue-in-cheek metrics:
  - On-point relevance to agenda topics
  - Bullshit score (lightheartedly detects corporate speak and non-substantive fluff)
  - Eloquence score (how fancy your words sound, regardless of content)
  - Unprofessionalism score (detecting casual language in formal settings)

- **Agenda Alignment**: Playfully compares the meeting transcript with the agenda to evaluate how quickly the conversation went off the rails

- **Joke Meeting Report Email**: Sends a formatted HTML email summarizing the "analysis" results with comedic flair

## Architecture

The module consists of several AWS Lambda functions orchestrated to process meeting transcripts:

1. **Orchestrator**: Triggered by new transcript uploads to S3, coordinates the analysis workflow
2. **Scoring Function**: Uses Amazon Bedrock to score participant contributions
3. **Agenda Alignment Function**: Analyzes how well the meeting followed the agenda
4. **Email Fanout Function**: Formats and sends email reports with the analysis results

## Integration with LMA

BullShrink integrates with the main LMA application by:

1. Monitoring the same S3 bucket where LMA stores meeting transcripts
2. Automatically triggering when a new transcript file with the format `<call-id>-TRANSCRIPT.txt` is uploaded
3. Processing the transcript and summary information
4. Sending an email report with analysis insights

## Deployment

To deploy the BullShrink module:

```bash
./deploy.sh [region] [s3-bucket-name] [sender-email] [recipient-email] [default-agenda]
```

### Parameters:

- **region**: AWS region (default: us-east-1)
- **s3-bucket-name**: S3 bucket where LMA transcripts are stored (default: lma-transcripts)
- **sender-email**: Email address used to send analysis reports (default: bullshrink@example.com)
- **recipient-email**: Email address to receive analysis reports (default: admin@example.com)
- **default-agenda**: Optional default agenda text to use when none is provided

## Requirements

- AWS CDK
- Python 3.12
- AWS SES configured with verified email addresses
- Amazon Bedrock access with required model permissions

## Configuration

### Meeting Agenda

You can provide a meeting agenda in one of three ways:

1. Include an `AgendaText` field in the direct Lambda invocation event
2. Upload a file named `[callId]-AGENDA.txt` to the S3 bucket along with the transcript
3. Specify a default agenda as a CloudFormation parameter during deployment

### Customization

You may need to modify the following files for customization:

- `scoring_lambda/app/main.py`: Adjust scoring criteria and weights
- `agenda_alignment_lambda/app/compare.py`: Customize agenda alignment logic
- `email_fanout_lambda/app/main.py`: Update email template and recipients

## Legal Disclaimer

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

**Important:** BullShrink is a joke module created purely for entertainment purposes during a hackathon. Any "analysis" it provides should not be used for actual performance evaluations, meeting assessments, or any serious business purpose. The scores and metrics it generates are not scientifically validated and are intended to be humorous rather than accurate or useful.

Created with 😂 during a hackathon event.