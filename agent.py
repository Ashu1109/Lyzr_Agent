import os
from google.adk import Agent
from google.adk.tools import transfer_to_agent
from openai_model import LiteLlm
from database import get_user_tokens
from data_science_agent import create_data_science_agent
from research_agent import create_research_agent
from memory_agent import create_memory_agent

# Define the Master Orchestrator Agent
def create_orchestrator(user_id: str):

    # 1. Retrieve User Tokens
    tokens = get_user_tokens(user_id)
    print(f"DEBUG: create_orchestrator tokens: {tokens.keys()}")

    # 2. Initialize Sub-Agents with proper descriptions for delegation
    data_science_agent = create_data_science_agent(tokens)
    research_agent = create_research_agent()
    memory_agent = create_memory_agent(user_id)

    # 3. Initialize the Master Agent with sub-agents
    model = LiteLlm(model='gpt-4o')

    agent = Agent(
        model=model,
        name='master_orchestrator',
        description='A master agent that orchestrates specialized sub-agents for data retrieval, research, and memory management.',
        instruction="""You are the Master Orchestrator Agent. Your role is to delegate tasks to specialized sub-agents.

**Available Sub-Agents:**
1. **data_science_agent**: Use this agent to retrieve data from the user's connected services (Gmail, Google Chat, Google Drive, Slack, GitHub).
   - Call this when the user asks about their emails, messages, files, repositories, or any internal data.

2. **research_agent**: Use this agent for web research and finding external information.
   - Call this when the user needs information from the internet or latest trends.

3. **memory_agent**: Use this agent for long-term memory storage and retrieval.
   - Call this when you need to remember user preferences or recall past context.

**Important Rules:**
- **Use transfer_to_agent** to delegate to the appropriate sub-agent.
- **Pass the full user query** to the appropriate agent - let the sub-agent handle the details.
- **After receiving the agent's response**, format it nicely and present it to the user.
- **Do NOT retry** if an agent returns an error - just inform the user.
- **Be concise** in your final response to the user.

**Workflow:**
1. Identify which agent(s) should handle the user's request
2. Call transfer_to_agent with the appropriate agent name
3. Present the results in a clear, user-friendly format
""",
        tools=[transfer_to_agent],
        sub_agents=[data_science_agent, research_agent, memory_agent]
    )

    return agent
