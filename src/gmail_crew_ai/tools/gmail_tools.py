import imaplib
import email
from email.header import decode_header
from typing import List, Tuple, Literal, Optional, Type, Dict, Any
import re
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
import os
from pydantic import BaseModel, Field
from crewai.tools import tool
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64

def decode_header_safe(header):
    """
    Safely decode email headers that might contain encoded words or non-ASCII characters.
    """
    if not header:
        return ""
    
    try:
        decoded_parts = []
        for decoded_str, charset in decode_header(header):
            if isinstance(decoded_str, bytes):
                if charset:
                    decoded_parts.append(decoded_str.decode(charset or 'utf-8', errors='replace'))
                else:
                    decoded_parts.append(decoded_str.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(str(decoded_str))
        return ' '.join(decoded_parts)
    except Exception as e:
        # Fallback to raw header if decoding fails
        return str(header)

def clean_email_body(email_body: str) -> str:
    """
    Clean the email body by removing HTML tags and excessive whitespace.
    """
    try:
        soup = BeautifulSoup(email_body, "html.parser")
        text = soup.get_text(separator=" ")  # Get text with spaces instead of <br/>
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        text = email_body  # Fallback to raw body if parsing fails

    # Remove excessive whitespace and newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text

class GmailToolBase(BaseTool):
    """Base class for Gmail tools, handling connection and credentials."""
    
    class Config:
        arbitrary_types_allowed = True

    email_address: Optional[str] = Field(None, description="Gmail email address")
    app_password: Optional[str] = Field(None, description="Gmail app password")

    def __init__(self, description: str = ""):
        super().__init__(description=description)
        self.email_address = os.environ.get("EMAIL_ADDRESS")
        self.app_password = os.environ.get("APP_PASSWORD")

        if not self.email_address or not self.app_password:
            raise ValueError("EMAIL_ADDRESS and APP_PASSWORD must be set in the environment.")

    def _connect(self):
        """Connect to Gmail."""
        try:
            print(f"Connecting to Gmail with email: {self.email_address[:3]}...{self.email_address[-8:]}")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(self.email_address, self.app_password)
            print("Successfully logged in to Gmail")
            return mail
        except Exception as e:
            print(f"Error connecting to Gmail: {e}")
            raise e

    def _disconnect(self, mail):
        """Disconnect from Gmail."""
        try:
            mail.close()
            mail.logout()
            print("Successfully disconnected from Gmail")
        except:
            pass

    def _get_thread_messages(self, mail: imaplib.IMAP4_SSL, msg) -> List[str]:
        """Get all messages in the thread by following References and In-Reply-To headers."""
        thread_messages = []
        
        # Get message IDs from References and In-Reply-To headers
        references = msg.get("References", "").split()
        in_reply_to = msg.get("In-Reply-To", "").split()
        message_ids = list(set(references + in_reply_to))  # Remove duplicates
        
        if message_ids:
            # Search for messages with these Message-IDs
            search_criteria = ' OR '.join(f'HEADER MESSAGE-ID "{mid}"' for mid in message_ids)
            result, data = mail.search(None, search_criteria)
            
            if result == "OK":
                thread_ids = data[0].split()
                for thread_id in thread_ids:
                    result, msg_data = mail.fetch(thread_id, "(RFC822)")
                    if result == "OK":
                        thread_msg = email.message_from_bytes(msg_data[0][1])
                        # Extract body from thread message
                        thread_body = self._extract_body(thread_msg)
                        thread_messages.append(thread_body)
        
        return thread_messages

    def _extract_body(self, msg) -> str:
        """Extract body from an email message."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                try:
                    email_body = part.get_payload(decode=True).decode()
                except:
                    email_body = ""

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body += email_body
                elif content_type == "text/html" and "attachment" not in content_disposition:
                    body += clean_email_body(email_body)
        else:
            try:
                body = clean_email_body(msg.get_payload(decode=True).decode())
            except Exception as e:
                body = f"Error decoding body: {e}"
        return body

class GetUnreadEmailsSchema(BaseModel):
    """Schema for GetUnreadEmailsTool input."""
    limit: Optional[int] = Field(
        default=5,
        description="Maximum number of unread emails to retrieve. Defaults to 5.",
        ge=1  # Ensures the limit is greater than or equal to 1
    )

class GetUnreadEmailsTool(GmailToolBase):
    """Tool to get unread emails from Gmail."""
    name: str = "get_unread_emails"
    description: str = "Gets unread emails from Gmail"
    args_schema: Type[BaseModel] = GetUnreadEmailsSchema
    
    def _run(self, limit: Optional[int] = 5) -> List[Tuple[str, str, str, str, Dict]]:
        mail = self._connect()
        try:
            print("DEBUG: Connecting to Gmail...")
            mail.select("INBOX")
            result, data = mail.search(None, 'UNSEEN')
            
            print(f"DEBUG: Search result: {result}")
            
            if result != "OK":
                print("DEBUG: Error searching for unseen emails")
                return []
            
            email_ids = data[0].split()
            print(f"DEBUG: Found {len(email_ids)} unread emails")
            
            if not email_ids:
                print("DEBUG: No unread emails found.")
                return []
            
            email_ids = list(reversed(email_ids))
            email_ids = email_ids[:limit]
            print(f"DEBUG: Processing {len(email_ids)} emails")
            
            emails = []
            for i, email_id in enumerate(email_ids):
                print(f"DEBUG: Processing email {i+1}/{len(email_ids)}")
                result, msg_data = mail.fetch(email_id, "(RFC822)")
                if result != "OK":
                    print(f"Error fetching email {email_id}:", result)
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Decode headers properly (handles encoded characters)
                subject = decode_header_safe(msg["Subject"])
                sender = decode_header_safe(msg["From"])
                
                # Extract and standardize the date
                date_str = msg.get("Date", "")
                received_date = self._parse_email_date(date_str)
                
                # Get the current message body
                current_body = self._extract_body(msg)
                
                # Get thread messages
                thread_messages = self._get_thread_messages(mail, msg)
                
                # Combine current message with thread history
                full_body = "\n\n--- Previous Messages ---\n".join([current_body] + thread_messages)

                # Get thread metadata
                thread_info = {
                    'message_id': msg.get('Message-ID', ''),
                    'in_reply_to': msg.get('In-Reply-To', ''),
                    'references': msg.get('References', ''),
                    'date': received_date,  # Use standardized date
                    'raw_date': date_str,   # Keep original date string
                    'email_id': email_id.decode('utf-8')
                }

                # Add a clear date indicator in the body for easier extraction
                full_body = f"EMAIL DATE: {received_date}\n\n{full_body}"
                
                # Print the structure of what we're appending
                print(f"DEBUG: Email tuple structure: subject={subject}, sender={sender}, body_length={len(full_body)}, email_id={email_id.decode('utf-8')}, thread_info_keys={thread_info.keys()}")
                
                emails.append((subject, sender, full_body, email_id.decode('utf-8'), thread_info))
            
            print(f"DEBUG: Returning {len(emails)} email tuples")
            return emails
        except Exception as e:
            print(f"DEBUG: Exception in GetUnreadEmailsTool: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            self._disconnect(mail)

    def _parse_email_date(self, date_str: str) -> str:
        """
        Parse email date string into a standardized format.
        Returns ISO format date string (YYYY-MM-DD) or empty string if parsing fails.
        """
        if not date_str:
            return ""
        
        try:
            # Try various date formats commonly found in emails
            # Remove timezone name if present (like 'EDT', 'PST')
            date_str = re.sub(r'\s+\([A-Z]{3,4}\)', '', date_str)
            
            # Parse with email.utils
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            if parsed_date:
                return parsed_date.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
        
        return ""

class SaveDraftSchema(BaseModel):
    """Schema for SaveDraftTool input."""
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content")
    recipient: str = Field(..., description="Recipient email address")
    thread_info: Optional[Dict[str, Any]] = Field(None, description="Thread information for replies")

class SaveDraftTool(BaseTool):
    """Tool to save an email as a draft using IMAP."""
    name: str = "save_email_draft"
    description: str = "Saves an email as a draft in Gmail"
    args_schema: Type[BaseModel] = SaveDraftSchema

    def _format_body(self, body: str) -> str:
        """Format the email body with signature."""
        # Replace [Your name] or [Your Name] with Tony Kipkemboi
        body = re.sub(r'\[Your [Nn]ame\]', 'Tony Kipkemboi', body)
        
        # If no placeholder was found, append the signature
        if '[Your' not in body and '[your' not in body:
            body = f"{body}\n\nBest regards,\nTony Kipkemboi"
        
        return body

    def _connect(self):
        """Connect to Gmail using IMAP."""
        # Get email credentials from environment
        email_address = os.environ.get('EMAIL_ADDRESS')
        app_password = os.environ.get('APP_PASSWORD')
        
        if not email_address or not app_password:
            raise ValueError("EMAIL_ADDRESS or APP_PASSWORD environment variables not set")
        
        # Connect to Gmail's IMAP server
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        print(f"Connecting to Gmail with email: {email_address[:3]}...{email_address[-10:]}")
        mail.login(email_address, app_password)
        return mail, email_address

    def _disconnect(self, mail):
        """Disconnect from Gmail."""
        try:
            mail.logout()
        except:
            pass

    def _check_drafts_folder(self, mail):
        """Check available mailboxes to find the drafts folder."""
        print("Checking available mailboxes...")
        result, mailboxes = mail.list()
        if result == 'OK':
            drafts_folders = []
            for mailbox in mailboxes:
                if b'Drafts' in mailbox or b'Draft' in mailbox:
                    drafts_folders.append(mailbox.decode())
                    print(f"Found drafts folder: {mailbox.decode()}")
            return drafts_folders
        return []

    def _verify_draft_saved(self, mail, subject, recipient):
        """Verify if the draft was actually saved by searching for it."""
        try:
            # Try different drafts folder names
            drafts_folders = [
                '"[Gmail]/Drafts"', 
                'Drafts',
                'DRAFTS',
                '"[Google Mail]/Drafts"',
                '[Gmail]/Drafts'
            ]
            
            for folder in drafts_folders:
                try:
                    print(f"Checking folder: {folder}")
                    result, _ = mail.select(folder, readonly=True)
                    if result != 'OK':
                        continue
                        
                    # Search for drafts with this subject
                    search_criteria = f'SUBJECT "{subject}"'
                    result, data = mail.search(None, search_criteria)
                    
                    if result == 'OK' and data[0]:
                        draft_count = len(data[0].split())
                        print(f"Found {draft_count} drafts matching subject '{subject}' in folder {folder}")
                        return True, folder
                    else:
                        print(f"No drafts found matching subject '{subject}' in folder {folder}")
                except Exception as e:
                    print(f"Error checking folder {folder}: {e}")
                    continue
                    
            return False, None
        except Exception as e:
            print(f"Error verifying draft: {e}")
            return False, None

    def _run(self, subject: str, body: str, recipient: str, thread_info: Optional[Dict[str, Any]] = None) -> str:
        try:
            mail, email_address = self._connect()
            
            # Check available drafts folders
            drafts_folders = self._check_drafts_folder(mail)
            print(f"Available drafts folders: {drafts_folders}")
            
            # Try with quoted folder name first
            drafts_folder = '"[Gmail]/Drafts"'
            print(f"Selecting drafts folder: {drafts_folder}")
            result, _ = mail.select(drafts_folder)
            
            # If that fails, try without quotes
            if result != 'OK':
                drafts_folder = '[Gmail]/Drafts'
                print(f"First attempt failed. Trying: {drafts_folder}")
                result, _ = mail.select(drafts_folder)
                
            # If that also fails, try just 'Drafts'
            if result != 'OK':
                drafts_folder = 'Drafts'
                print(f"Second attempt failed. Trying: {drafts_folder}")
                result, _ = mail.select(drafts_folder)
                
            if result != 'OK':
                return f"Error: Could not select drafts folder. Available folders: {drafts_folders}"
                
            print(f"Successfully selected drafts folder: {drafts_folder}")
            
            # Format body and add signature
            body_with_signature = self._format_body(body)
            
            # Create the email message
            message = email.message.EmailMessage()
            message["From"] = email_address
            message["To"] = recipient
            message["Subject"] = subject
            message.set_content(body_with_signature)
            print(f"Created message with subject: {subject}")

            # Add thread headers if this is a reply
            if thread_info:
                # References header should include all previous message IDs
                references = []
                if thread_info.get('references'):
                    references.extend(thread_info['references'].split())
                if thread_info.get('message_id'):
                    references.append(thread_info['message_id'])
                
                if references:
                    message["References"] = " ".join(references)
                
                # In-Reply-To should point to the immediate parent message
                if thread_info.get('message_id'):
                    message["In-Reply-To"] = thread_info['message_id']

                # Make sure subject has "Re: " prefix
                if not subject.lower().startswith('re:'):
                    message["Subject"] = f"Re: {subject}"
                    
                print(f"Added thread information for reply")

            # Save to drafts
            print(f"Attempting to save draft to {drafts_folder}...")
            date = imaplib.Time2Internaldate(time.time())
            result, data = mail.append(drafts_folder, '\\Draft', date, message.as_bytes())
            
            if result != 'OK':
                return f"Error saving draft: {result}, {data}"
                
            print(f"Draft save attempt result: {result}")
            
            # Verify the draft was actually saved
            verified, folder = self._verify_draft_saved(mail, subject, recipient)
            
            if verified:
                return f"VERIFIED: Draft email saved with subject: '{subject}' in folder {folder}"
            else:
                # Try Gmail's API approach as a fallback
                try:
                    # Try saving directly to All Mail and flagging as draft
                    result, data = mail.append('[Gmail]/All Mail', '\\Draft', date, message.as_bytes())
                    if result == 'OK':
                        return f"Draft saved to All Mail with subject: '{subject}' (flagged as draft)"
                    else:
                        return f"WARNING: Draft save attempt returned {result}, but verification failed. Please check your Gmail Drafts folder."
                except Exception as e:
                    return f"WARNING: Draft may not have been saved properly: {str(e)}"

        except Exception as e:
            return f"Error saving draft: {str(e)}"
        finally:
            self._disconnect(mail)

class GmailOrganizeSchema(BaseModel):
    """Schema for GmailOrganizeTool input."""
    email_id: str = Field(..., description="Email ID to organize")
    category: str = Field(..., description="Category assigned by agent (Urgent/Response Needed/etc)")
    priority: str = Field(..., description="Priority level (High/Medium/Low)")
    should_star: bool = Field(default=False, description="Whether to star the email")
    labels: List[str] = Field(default_list=[], description="Labels to apply")

class GmailOrganizeTool(GmailToolBase):
    """Tool to organize emails based on agent categorization."""
    name: str = "organize_email"
    description: str = "Organizes emails using Gmail's priority features based on category and priority"
    args_schema: Type[BaseModel] = GmailOrganizeSchema

    def _run(self, email_id: str, category: str, priority: str, should_star: bool = False, labels: List[str] = None) -> str:
        """Organize an email with the specified parameters."""
        if labels is None:
            # Provide a default empty list to avoid validation errors
            labels = []
        
        print(f"Organizing email {email_id} with category {category}, priority {priority}, star={should_star}, labels={labels}")
        
        mail = self._connect()
        try:
            # Select inbox to ensure we can access the email
            mail.select("INBOX")
            
            # Apply organization based on category and priority
            if category == "Urgent Response Needed" and priority == "High":
                # Star the email
                if should_star:
                    mail.store(email_id, '+FLAGS', '\\Flagged')
                
                # Mark as important
                mail.store(email_id, '+FLAGS', '\\Important')
                
                # Apply URGENT label if it doesn't exist
                if "URGENT" not in labels:
                    labels.append("URGENT")

            # Apply all specified labels
            for label in labels:
                try:
                    # Create label if it doesn't exist
                    mail.create(label)
                except:
                    pass  # Label might already exist
                
                # Apply label
                mail.store(email_id, '+X-GM-LABELS', label)

            return f"Email organized: Starred={should_star}, Labels={labels}"

        except Exception as e:
            return f"Error organizing email: {e}"
        finally:
            self._disconnect(mail)

class GmailDeleteSchema(BaseModel):
    """Schema for GmailDeleteTool input."""
    email_id: str = Field(..., description="Email ID to delete")
    reason: str = Field(..., description="Reason for deletion")

class GmailDeleteTool(BaseTool):
    """Tool to delete an email using IMAP."""
    name: str = "delete_email"
    description: str = "Deletes an email from Gmail"
    
    def _run(self, email_id: str, reason: str) -> str:
        """
        Delete an email by ID.
        Parameters:
            email_id: The email ID to delete
            reason: The reason for deletion (for logging)
        """
        try:
            # Validate inputs - Add this validation
            if not email_id or not isinstance(email_id, str):
                return f"Error: Invalid email_id format: {email_id}"
            
            if not reason or not isinstance(reason, str):
                return f"Error: Invalid reason format: {reason}"
                
            mail = self._connect()
            try:
                mail.select("INBOX")
                
                # First verify the email exists and get its details for logging
                result, data = mail.fetch(email_id, "(RFC822)")
                if result != "OK" or not data or data[0] is None:
                    return f"Error: Email with ID {email_id} not found"
                    
                msg = email.message_from_bytes(data[0][1])
                subject = decode_header_safe(msg["Subject"])
                sender = decode_header_safe(msg["From"])
                
                # Move to Trash
                mail.store(email_id, '+X-GM-LABELS', '\\Trash')
                mail.store(email_id, '-X-GM-LABELS', '\\Inbox')
                
                return f"Email deleted: '{subject}' from {sender}. Reason: {reason}"
            except Exception as e:
                return f"Error deleting email: {e}"
            finally:
                self._disconnect(mail)

        except Exception as e:
            return f"Error deleting email: {str(e)}"

class EmptyTrashTool(BaseTool):
    """Tool to empty Gmail trash."""
    name: str = "empty_gmail_trash"
    description: str = "Empties the Gmail trash folder to free up space"

    def _connect(self):
        """Connect to Gmail using IMAP."""
        # Get email credentials from environment
        email_address = os.environ.get('EMAIL_ADDRESS')
        app_password = os.environ.get('APP_PASSWORD')
        
        if not email_address or not app_password:
            raise ValueError("EMAIL_ADDRESS or APP_PASSWORD environment variables not set")
        
        # Connect to Gmail's IMAP server
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        print(f"Connecting to Gmail with email: {email_address[:3]}...{email_address[-10:]}")
        mail.login(email_address, app_password)
        return mail

    def _disconnect(self, mail):
        """Disconnect from Gmail."""
        try:
            mail.logout()
        except:
            pass
    
    def _run(self) -> str:
        """Empty the Gmail trash folder."""
        try:
            mail = self._connect()
            
            # Try different trash folder names (Gmail can have different naming conventions)
            trash_folders = [
                '"[Gmail]/Trash"',
                '[Gmail]/Trash',
                'Trash',
                '"[Google Mail]/Trash"',
                '[Google Mail]/Trash'
            ]
            
            success = False
            trash_folder_used = None
            
            for folder in trash_folders:
                try:
                    print(f"Attempting to select trash folder: {folder}")
                    result, data = mail.select(folder)
                    
                    if result == 'OK':
                        trash_folder_used = folder
                        print(f"Successfully selected trash folder: {folder}")
                        
                        # Search for all messages in trash
                        result, data = mail.search(None, 'ALL')
                        
                        if result == 'OK':
                            email_ids = data[0].split()
                            count = len(email_ids)
                            
                            if count == 0:
                                print("No messages found in trash.")
                                return "Trash is already empty. No messages to delete."
                            
                            print(f"Found {count} messages in trash.")
                            
                            # Delete all messages in trash
                            for email_id in email_ids:
                                mail.store(email_id, '+FLAGS', '\\Deleted')
                            
                            # Permanently remove messages marked for deletion
                            mail.expunge()
                            success = True
                            break
                        
                except Exception as e:
                    print(f"Error accessing trash folder {folder}: {e}")
                    continue
            
            if success:
                return f"Successfully emptied Gmail trash folder ({trash_folder_used}). Deleted {count} messages."
            else:
                return "Could not empty trash. No trash folder found or accessible."

        except Exception as e:
            return f"Error emptying trash: {str(e)}"
        finally:
            self._disconnect(mail)