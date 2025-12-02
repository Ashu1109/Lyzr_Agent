from google.adk import Agent
from openai_model import LiteLlm
from memory import add_memory, query_memory

def create_memory_agent(user_id: str):
    """
    Creates a Memory Agent with access to Supermemory.
    """
    
    def memory_tool(query: str):
        """Retrieves past context and memories relevant to the query."""
        return query_memory(query)

    def save_context_tool(content: str):
        """Saves important information (user preferences, project details, social context) to long-term memory."""
        return add_memory(content, metadata={"source": "agent_interaction", "user_id": user_id})

    model = LiteLlm(model='gpt-4o')
    
    agent = Agent(
        model=model,
        name="memory_agent",
        description="""An agent that can store and retrieve long-term memories.",
        You are a Memory Agent responsible for managing long-term memory.
        
        **Your Capabilities:**
        1.  **Retrieve Memory**: Search for past context using 'memory_tool'.
        2.  **Save Memory**: Store new important information using 'save_context_tool'.
        
        **Instructions:**
        - **Recall**: When asked to recall something, use 'memory_tool'.
        - **Store**: When asked to remember or save something, use 'save_context_tool'.
        - **Summarize**: If you find relevant memories, summarize them clearly for the user.
        """,
        tools=[memory_tool, save_context_tool]
    )
    
    return agent
