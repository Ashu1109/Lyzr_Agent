from google.adk import Agent
from openai_model import LiteLlm
from tools.search_tool import search_web
from tools.scrape_tool import scrape_website

def create_research_agent():
    model = LiteLlm(model='gpt-4o')
    
    agent = Agent(
        model=model,
        name="research_agent",
        description="""An agent capable of performing deep research by searching the web and scraping content.",
        You are a Deep Research Agent. Your goal is to provide comprehensive answers by researching the web.
        
        **Instructions:**
        1.  **Analyze**: Identify key search terms from the user's request.
        2.  **Search**: Use 'search_web' to find relevant sources.
        3.  **Scrape**: Use 'scrape_website' to gather details from promising search results.
        4.  **Synthesize**: Combine findings into a detailed report.
        5.  **Cite**: Always cite your sources with URLs.
        """,
        tools=[search_web, scrape_website]
    )
    
    return agent
