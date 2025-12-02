from google.adk import Agent
from openai_model import LiteLlm
from tools.drive_tool import list_files, search_files
from tools.slack_tool import list_channels, search_messages
from tools.github_tool import list_repos, search_repos
from tools.gmail_tool import list_emails, get_email_content
from tools.google_chat_tool import list_spaces, list_messages

def create_data_science_agent(tokens: dict):
    """
    Creates a Data Science Agent with access to Gmail, Google Chat, Google Drive, Slack, and GitHub.
    """

    # --- Tool Wrappers with Token Injection ---

    def gmail_list_emails_tool(query: str = ""):
        """Lists recent emails from Gmail. Query can be 'label:inbox' or search terms."""
        token = tokens.get('gmail')
        if not token:
            return "Error: Gmail not connected."
        return list_emails(token, query if query else "label:inbox")

    def gmail_get_content_tool(message_id: str):
        """Gets the content of a specific email by ID."""
        token = tokens.get('gmail')
        if not token:
            return "Error: Gmail not connected."
        return get_email_content(token, message_id)

    def chat_list_spaces_tool():
        """Lists Google Chat spaces."""
        token = tokens.get('google_chat')
        if not token:
            return "Error: Google Chat not connected."
        return list_spaces(token)

    def chat_list_messages_tool(space_name: str):
        """Lists messages in a Google Chat space."""
        token = tokens.get('google_chat')
        if not token:
            return "Error: Google Chat not connected."
        return list_messages(token, space_name)

    def drive_list_files_tool(query: str = ""):
        """Lists the most recent files from Google Drive."""
        token = tokens.get('google_drive')
        if not token:
            return "Error: Google Drive not connected."
        return list_files(token)

    def drive_search_files_tool(query: str):
        """Searches for files in Google Drive."""
        token = tokens.get('google_drive')
        if not token:
            return "Error: Google Drive not connected."
        return search_files(token, query)

    def slack_list_channels_tool(query: str = ""):
        """Lists all public channels in the Slack workspace."""
        token = tokens.get('slack')
        if not token:
            return "Error: Slack not connected."
        return list_channels(token)

    def slack_search_messages_tool(query: str):
        """Searches for messages in Slack."""
        token = tokens.get('slack')
        if not token:
            return "Error: Slack not connected."
        return search_messages(token, query)

    def github_list_repos_tool(query: str = ""):
        """Lists the user's GitHub repositories."""
        token = tokens.get('github')
        if not token:
            return "Error: GitHub not connected."
        return list_repos(token)

    def github_search_repos_tool(query: str):
        """Searches for GitHub repositories."""
        token = tokens.get('github')
        if not token:
            return "Error: GitHub not connected."
        return search_repos(token, query)

    # --- Agent Definition ---

    model = LiteLlm(model='gpt-4o')

    agent = Agent(
        model=model,
        name="data_science_agent",
        description="Specialist agent for retrieving data from Gmail, Google Chat, Google Drive, Slack, and GitHub.",
        instruction="""You are a Data Science Agent that retrieves data from the user's connected services.

**Your Tools:**
- **Gmail**: gmail_list_emails_tool (list emails), gmail_get_content_tool (read specific email)
- **Google Chat**: chat_list_spaces_tool (list spaces), chat_list_messages_tool (read messages from a space)
- **Google Drive**: drive_list_files_tool (list files), drive_search_files_tool (search files)
- **Slack**: slack_list_channels_tool (list channels), slack_search_messages_tool (search messages)
- **GitHub**: github_list_repos_tool (list repositories), github_search_repos_tool (search repositories)

**Process:**
1. **Analyze the request**: Identify which services the user wants data from.
2. **Call tools ONCE**: For each service requested, call the appropriate list tool exactly once.
3. **Format results**: After ALL tool calls complete, organize and present the data cleanly.
4. **STOP**: Do not call tools again. Present your final answer.

**Rules:**
- Call each tool a maximum of ONE time per request.
- **If a tool returns "Error: [Service] not connected"**, you MUST return the error message back to the Master Orchestrator.
  - DO NOT try alternative services or retry
  - Simply return the error so the user can be informed they need to connect that service
- Present results in a clean, bulleted format with relevant details.
- After gathering all requested data, immediately provide your final formatted response.
""",
        tools=[
            gmail_list_emails_tool, gmail_get_content_tool,
            chat_list_spaces_tool, chat_list_messages_tool,
            drive_list_files_tool, drive_search_files_tool,
            slack_list_channels_tool, slack_search_messages_tool,
            github_list_repos_tool, github_search_repos_tool
        ]
    )

    return agent
