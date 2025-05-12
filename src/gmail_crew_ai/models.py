from pydantic import BaseModel, Field, SkipValidation
from typing import List, Optional, Dict, Literal, Callable, Any
from datetime import datetime

class EmailDetails(BaseModel):
    """Model for email details."""
    email_id: Optional[str] = Field(None, description="Email ID")
    subject: Optional[str] = Field(None, description="Email subject")
    sender: Optional[str] = Field(None, description="Email sender")
    body: Optional[str] = Field(None, description="Email body")
    date: Optional[str] = Field(None, description="Email date (YYYY-MM-DD)")
    age_days: Optional[int] = Field(None, description="Age of the email in days from today")
    thread_info: Optional[Dict[str, Any]] = Field(None, description="Thread information")
    is_part_of_thread: Optional[bool] = Field(False, description="Whether this email is part of a thread")
    thread_size: Optional[int] = Field(1, description="Number of emails in this thread")
    thread_position: Optional[int] = Field(1, description="Position of this email in the thread (1 = first)")

    @classmethod
    def from_email_tuple(cls, email_tuple):
        """Create an EmailDetails from an email tuple."""
        if not email_tuple or len(email_tuple) < 5:
            return cls(email_id=None, subject=None)
        
        subject, sender, body, email_id, thread_info = email_tuple
        
        # Extract date from thread_info
        date = ""
        if isinstance(thread_info, dict) and 'date' in thread_info:
            date = thread_info['date']
            
        return cls(
            email_id=email_id,
            subject=subject,
            sender=sender,
            body=body,
            date=date,
            thread_info=thread_info
        )

# Define the valid categories, priorities, and actions as type aliases
EmailCategoryType = Literal["NEWSLETTERS", "PROMOTIONS", "PERSONAL", "GITHUB", 
                           "SPONSORSHIPS", "RECRUITMENT", "COLD_EMAIL", 
                           "EVENT_INVITATIONS", "RECEIPTS_INVOICES", "YOUTUBE", "SOCIALS"]

EmailPriorityType = Literal["HIGH", "MEDIUM", "LOW"]

EmailActionType = Literal["REPLY", "READ_ONLY", "TASK", "IGNORE"]

class CategorizedEmail(BaseModel):
    """Model for categorized email information."""
    email_id: str = Field(..., description="Unique identifier for the email")
    subject: str = Field(..., description="Email subject line")
    sender: str = Field(..., description="Email sender (name and address)")
    date: str = Field(..., description="Email date in YYYY-MM-DD format")
    category: EmailCategoryType = Field(..., description="Category of the email")
    priority: EmailPriorityType = Field(..., description="Priority level of the email")
    required_action: EmailActionType = Field(..., description="Required action for the email")
    reason: str = Field(..., description="Reason for the categorization")
    due_date: Optional[str] = Field(None, description="Due date for action if applicable")
    thread_info: Optional[Dict] = Field(default=None, description="Thread information for replies")

class OrganizedEmail(BaseModel):
    """Model for organized email information."""
    email_id: str = Field(..., description="Unique identifier for the email")
    subject: str = Field(..., description="Email subject line")
    applied_labels: List[str] = Field(default_factory=list, description="Labels applied to the email")
    starred: bool = Field(default=False, description="Whether the email was starred")
    result: str = Field(..., description="Result of the organization attempt")

class EmailResponse(BaseModel):
    """Model for email response information."""
    email_id: str = Field(..., description="Unique identifier for the email")
    subject: str = Field(..., description="Email subject line")
    recipient: str = Field(..., description="Email recipient")
    response_summary: str = Field(..., description="Summary of the response")
    response_needed: bool = Field(..., description="Whether a response was needed")
    draft_saved: bool = Field(default=False, description="Whether a draft was saved")

class SlackNotification(BaseModel):
    """Model for Slack notification information."""
    email_id: str = Field(..., description="Unique identifier for the email")
    subject: str = Field(..., description="Email subject line")
    sender: str = Field(..., description="Email sender")
    category: EmailCategoryType = Field(..., description="Category of the email")
    priority: EmailPriorityType = Field(..., description="Priority level of the email")
    summary: str = Field(..., description="Brief summary of the email content")
    action_needed: Optional[str] = Field(None, description="Action needed, if any")
    headline: str = Field(..., description="Custom headline for the notification")
    intro: str = Field(..., description="Custom intro phrase for the notification")
    action_header: Optional[str] = Field(None, description="Custom header for the action section")
    notification_sent: bool = Field(default=False, description="Whether notification was sent")

class EmailCleanupInfo(BaseModel):
    """Model for email cleanup information."""
    email_id: str = Field(..., description="Unique identifier for the email")
    subject: str = Field(..., description="Email subject line")
    sender: str = Field(..., description="Email sender")
    age_days: int = Field(..., description="Age of the email in days")
    deleted: bool = Field(..., description="Whether the email was deleted")
    reason: str = Field(..., description="Reason for deletion or preservation")

class SimpleCategorizedEmail(BaseModel):
    """Simplified model for debugging."""
    email_id: Optional[str] = Field(None, description="Unique identifier for the email")
    subject: Optional[str] = Field(None, description="Email subject line")
    sender: Optional[str] = Field(None, description="Email sender address")
    category: Optional[str] = Field(None, description="Category of the email")
    priority: Optional[str] = Field(None, description="Priority level of the email")
    required_action: Optional[str] = Field(None, description="Required action for the email")
    date: Optional[str] = Field(None, description="Date the email was received (YYYY-MM-DD)")
    age_days: Optional[int] = Field(None, description="Age of the email in days from today")

    # Update the from_email_tuple method to include date
    @classmethod
    def from_email_tuple(cls, email_tuple):
        """Create a SimpleCategorizedEmail from an email tuple."""
        if not email_tuple or len(email_tuple) < 5:
            return cls(email_id=None, subject=None)
        
        subject, sender, body, email_id, thread_info = email_tuple
        
        # Extract date from body or thread_info
        date = ""
        if isinstance(thread_info, dict) and 'date' in thread_info:
            date = thread_info['date']
        elif body and body.startswith("EMAIL DATE:"):
            date_line = body.split("\n")[0]
            date = date_line.replace("EMAIL DATE:", "").strip()
        
        return cls(
            email_id=email_id,
            subject=subject,
            sender=sender,
            date=date
        )
