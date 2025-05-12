from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai_tools import FileReadTool
import json
import os
from typing import List, Dict, Any, Callable
from pydantic import SkipValidation
from datetime import date, datetime

from gmail_crew_ai.tools.gmail_tools import GetUnreadEmailsTool, SaveDraftTool, GmailOrganizeTool, GmailDeleteTool, EmptyTrashTool
from gmail_crew_ai.tools.slack_tool import SlackNotificationTool
from gmail_crew_ai.tools.date_tools import DateCalculationTool
from gmail_crew_ai.models import CategorizedEmail, OrganizedEmail, EmailResponse, SlackNotification, EmailCleanupInfo, SimpleCategorizedEmail, EmailDetails

@CrewBase
class GmailCrewAi():
	"""Crew that processes emails."""
	agents_config = 'config/agents.yaml'
	tasks_config = 'config/tasks.yaml'

	@before_kickoff
	def fetch_emails(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
		"""Fetch emails before starting the crew and calculate ages."""
		print("Fetching emails before starting the crew...")
		
		# Get the email limit from inputs
		email_limit = inputs.get('email_limit', 5)
		print(f"Fetching {email_limit} emails...")
		
		# Create the output directory if it doesn't exist
		os.makedirs("output", exist_ok=True)
		
		# Use the GetUnreadEmailsTool directly
		email_tool = GetUnreadEmailsTool()
		email_tuples = email_tool._run(limit=email_limit)
		
		# Convert email tuples to EmailDetails objects with pre-calculated ages
		emails = []
		today = date.today()
		for email_tuple in email_tuples:
			email_detail = EmailDetails.from_email_tuple(email_tuple)
			
			# Calculate age if date is available
			if email_detail.date:
				try:
					email_date_obj = datetime.strptime(email_detail.date, "%Y-%m-%d").date()
					email_detail.age_days = (today - email_date_obj).days
					print(f"Email date: {email_detail.date}, age: {email_detail.age_days} days")
				except Exception as e:
					print(f"Error calculating age for email date {email_detail.date}: {e}")
					email_detail.age_days = None
			
			emails.append(email_detail.dict())
		
		# Save emails to file
		with open('output/fetched_emails.json', 'w') as f:
			json.dump(emails, f, indent=2)
		
		print(f"Fetched and saved {len(emails)} emails to output/fetched_emails.json")
		
		return inputs
	
	llm = LLM(
		model="gemini/gemini-2.0-flash",
		api_key=os.getenv("GEMINI_API_KEY"),
	)

	@agent
	def categorizer(self) -> Agent:
		"""The email categorizer agent."""
		return Agent(
			config=self.agents_config['categorizer'],
			tools=[FileReadTool()],
			llm=self.llm,
		)

	@agent
	def organizer(self) -> Agent:
		"""The email organization agent."""
		return Agent(
			config=self.agents_config['organizer'],
			tools=[GmailOrganizeTool(), FileReadTool()],
			llm=self.llm,
		)
		
	@agent
	def response_generator(self) -> Agent:
		"""The email response generator agent."""
		return Agent(
			config=self.agents_config['response_generator'],
			tools=[SaveDraftTool()],
			llm=self.llm,
		)
	
	@agent
	def notifier(self) -> Agent:
		"""The email notification agent."""
		return Agent(
			config=self.agents_config['notifier'],
			tools=[SlackNotificationTool()],
			llm=self.llm,
		)

	@agent
	def cleaner(self) -> Agent:
		"""The email cleanup agent."""
		return Agent(
			config=self.agents_config['cleaner'],
			tools=[GmailDeleteTool(), EmptyTrashTool()],
			llm=self.llm,
		)

	@task
	def categorization_task(self) -> Task:
		"""The email categorization task."""
		return Task(
			config=self.tasks_config['categorization_task'],
			output_pydantic=SimpleCategorizedEmail
		)
	
	@task
	def organization_task(self) -> Task:
		"""The email organization task."""
		return Task(
			config=self.tasks_config['organization_task'],
			output_pydantic=OrganizedEmail,
		)

	@task
	def response_task(self) -> Task:
		"""The email response task."""
		return Task(
			config=self.tasks_config['response_task'],
			output_pydantic=EmailResponse,
		)
	
	@task
	def notification_task(self) -> Task:
		"""The email notification task."""
		return Task(
			config=self.tasks_config['notification_task'],
			output_pydantic=SlackNotification,
		)

	@task
	def cleanup_task(self) -> Task:
		"""The email cleanup task."""
		return Task(
			config=self.tasks_config['cleanup_task'],
			output_pydantic=EmailCleanupInfo,
		)

	@crew
	def crew(self) -> Crew:
		"""Creates the email processing crew."""
		return Crew(
			agents=self.agents,
			tasks=self.tasks,
			process=Process.sequential,
			verbose=True
		)

	def _debug_callback(self, event_type, payload):
		"""Debug callback for crew events."""
		if event_type == "task_start":
			print(f"DEBUG: Starting task: {payload.get('task_name')}")
		elif event_type == "task_end":
			print(f"DEBUG: Finished task: {payload.get('task_name')}")
			print(f"DEBUG: Task output type: {type(payload.get('output'))}")
			
			# Add more detailed output inspection
			output = payload.get('output')
			if output:
				if isinstance(output, dict):
					print(f"DEBUG: Output keys: {output.keys()}")
					for key, value in output.items():
						print(f"DEBUG: {key}: {value[:100] if isinstance(value, str) and len(value) > 100 else value}")
				elif isinstance(output, list):
					print(f"DEBUG: Output list length: {len(output)}")
					if output and len(output) > 0:
						print(f"DEBUG: First item type: {type(output[0])}")
						if isinstance(output[0], dict):
							print(f"DEBUG: First item keys: {output[0].keys()}")
				else:
					print(f"DEBUG: Output: {str(output)[:200]}...")
		elif event_type == "agent_start":
			print(f"DEBUG: Agent starting: {payload.get('agent_name')}")
		elif event_type == "agent_end":
			print(f"DEBUG: Agent finished: {payload.get('agent_name')}")
		elif event_type == "error":
			print(f"DEBUG: Error: {payload.get('error')}")

	def _validate_categorization_output(self, output):
		"""Validate the categorization output before writing to file."""
		print(f"DEBUG: Validating categorization output: {output}")
		
		# If output is empty or invalid, provide a default
		if not output:
			print("WARNING: Empty categorization output, providing default")
			return {
				"email_id": "",
				"subject": "",
				"category": "",
				"priority": "",
				"required_action": ""
			}
		
		# If output is a string (which might happen if the LLM returns JSON as a string)
		if isinstance(output, str):
			try:
				# Try to parse it as JSON
				import json
				# First, check if the string starts with "my best complete final answer"
				if "my best complete final answer" in output.lower():
					# Extract the JSON part
					json_start = output.find("{")
					json_end = output.rfind("}") + 1
					if json_start >= 0 and json_end > json_start:
						json_str = output[json_start:json_end]
						parsed = json.loads(json_str)
						print("DEBUG: Successfully extracted and parsed JSON from answer")
						return parsed
				
				# Try to parse the whole string as JSON
				parsed = json.loads(output)
				print("DEBUG: Successfully parsed string output as JSON")
				return parsed
			except Exception as e:
				print(f"WARNING: Output is a string but not valid JSON: {e}")
				# Try to extract anything that looks like JSON
				import re
				json_pattern = r'\{.*\}'
				match = re.search(json_pattern, output, re.DOTALL)
				if match:
					try:
						json_str = match.group(0)
						parsed = json.loads(json_str)
						print("DEBUG: Successfully extracted and parsed JSON using regex")
						return parsed
					except:
						print("WARNING: Failed to parse extracted JSON")
		
		# If output is already a dict, make sure it has the required fields
		if isinstance(output, dict):
			required_fields = ["email_id", "subject", "category", "priority", "required_action"]
			missing_fields = [field for field in required_fields if field not in output]
			
			if missing_fields:
				print(f"WARNING: Output missing required fields: {missing_fields}")
				# Add missing fields with empty values
				for field in missing_fields:
					output[field] = ""
			
			# Check if the values match the expected format
			if output.get("email_id") == "12345" and output.get("subject") == "Urgent Task Update":
				print("WARNING: Output contains placeholder values, trying to fix")
				# Try to get the real email ID from the fetched emails
				try:
					with open("output/fetched_emails.json", "r") as f:
						fetched_emails = json.load(f)
						if fetched_emails and len(fetched_emails) > 0:
							real_email = fetched_emails[0]
							output["email_id"] = real_email.get("email_id", "")
							output["subject"] = real_email.get("subject", "")
				except Exception as e:
					print(f"WARNING: Failed to fix placeholder values: {e}")
		
		return output
