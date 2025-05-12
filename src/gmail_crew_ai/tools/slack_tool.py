import os
import json
import requests
from typing import List, Dict, Optional, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

class SlackNotificationSchema(BaseModel):
    """Schema for SlackNotificationTool input."""
    subject: str = Field(..., description="Email subject")
    sender: str = Field(..., description="Email sender")
    category: str = Field(..., description="Email category")
    priority: str = Field(..., description="Email priority")
    summary: str = Field(..., description="Brief summary of the email content")
    action_needed: Optional[str] = Field(None, description="Action needed, if any")
    headline: Optional[str] = Field(None, description="Custom headline for the notification")
    intro: Optional[str] = Field(None, description="Custom intro phrase for the notification")
    action_header: Optional[str] = Field(None, description="Custom header for the action section")

class SlackNotificationTool(BaseTool):
    """Tool to send notifications to Slack."""
    name: str = "slack_notification"
    description: str = "Sends notifications about important emails to Slack"
    args_schema: Type[BaseModel] = SlackNotificationSchema
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self):
        super().__init__()
        self._webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        if not self._webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL must be set in the environment.")

    def _run(self, subject: str, sender: str, category: str, 
             priority: str, summary: str, action_needed: Optional[str] = None,
             headline: Optional[str] = None, intro: Optional[str] = None,
             action_header: Optional[str] = None) -> str:
        """Send a notification to Slack."""
        
        # Format the message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": headline or f"Important Email: {subject}"
                }
            }
        ]
        
        # Add intro if provided
        if intro:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{intro}*"
                }
            })
        
        # Add email details
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*From:*\n{sender}"},
                {"type": "mrkdwn", "text": f"*Category:*\n{category}"},
                {"type": "mrkdwn", "text": f"*Priority:*\n{priority}"},
            ]
        })
        
        # Add summary
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary:*\n{summary}"
            }
        })
        
        # Add action needed if provided
        if action_needed:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{action_header or 'Action Needed:'}*\n{action_needed}"
                }
            })
        
        # Add divider
        blocks.append({"type": "divider"})
        
        # Prepare the payload
        payload = {
            "blocks": blocks
        }
        
        # Send the notification
        try:
            response = requests.post(
                self._webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return f"Slack notification sent successfully for email: {subject}"
        except Exception as e:
            return f"Error sending Slack notification: {e}" 