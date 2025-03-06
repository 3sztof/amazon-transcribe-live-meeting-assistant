#!/bin/bash
set -e

# Install uv package manager if not already installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Define default parameters
DEFAULT_REGION="us-east-1"
DEFAULT_BUCKET_NAME="lma-transcripts"
DEFAULT_SENDER="bullshrink@example.com"
DEFAULT_RECIPIENT="admin@example.com"
DEFAULT_AGENDA=""

# Parse command line arguments
REGION=${1:-$DEFAULT_REGION}
S3_BUCKET=${2:-$DEFAULT_BUCKET_NAME}
SENDER_EMAIL=${3:-$DEFAULT_SENDER}
RECIPIENT_EMAIL=${4:-$DEFAULT_RECIPIENT}
AGENDA_TEXT=${5:-$DEFAULT_AGENDA}

echo "===========================================" 
echo "Deploying LMA BullShrink stack..."
echo "DISCLAIMER: BullShrink is a joke module created during"
echo "a hackathon event."
echo "This module is for entertainment purposes only!"
echo "===========================================" 
echo "AWS Region: $REGION"
echo "Target S3 Bucket: $S3_BUCKET"
echo "Sender Email: $SENDER_EMAIL"
echo "Recipient Email: $RECIPIENT_EMAIL"
if [ -n "$AGENDA_TEXT" ]; then
  echo "Default Agenda: $AGENDA_TEXT"
else
  echo "Default Agenda: (none)"
fi
echo "===========================================" 

# Deploy the CDK stack with parameters
uv run cdk deploy \
    --parameters CallTranscriptsBucketName=$S3_BUCKET \
    --parameters SenderEmailParam=$SENDER_EMAIL \
    --parameters RecipientEmailParam=$RECIPIENT_EMAIL \
    --parameters DefaultAgendaParam="$AGENDA_TEXT" \
    --region $REGION

echo "===========================================" 
echo "Deployment complete!"
echo "===========================================" 
echo "To integrate with LMA main application:"
echo "1. Ensure your LMA application saves transcripts to: $S3_BUCKET"
echo "2. File naming convention should be: <call-id>-TRANSCRIPT.txt"
echo "3. BullShrink will automatically process new transcripts"
echo "4. Check your CloudWatch logs to verify functionality"
echo "===========================================" 
echo "REMEMBER: BullShrink is a joke module created during"
echo "a hackathon event. Any 'insights'"
echo "it provides should be taken with a large grain of salt!"
echo "===========================================" 