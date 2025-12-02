import os
from dotenv import load_dotenv
from supermemory import Supermemory

load_dotenv()

SUPERMEMORY_API_KEY = os.getenv("SUPERMEMORY_API_KEY")

def get_client():
    if not SUPERMEMORY_API_KEY:
        print("Warning: SUPERMEMORY_API_KEY not set.")
        return None
    return Supermemory(api_key=SUPERMEMORY_API_KEY)

def add_memory(content: str, metadata: dict = None):
    """
    Adds a memory to Supermemory.ai using the SDK.
    """
    client = get_client()
    if not client:
        return None

    try:
        # Using the SDK's add method with keyword arguments (verified via inspection)
        response = client.memories.add(content=content, metadata=metadata or {})
        # Convert MemoryAddResponse object to a dictionary to ensure JSON serializability
        return {"id": getattr(response, "id", None), "status": getattr(response, "status", None)}
    except Exception as e:
        print(f"Error adding memory with SDK: {e}")
        return None

def query_memory(query: str, limit: int = 5):
    """
    Queries Supermemory.ai for relevant context using the SDK.
    """
    client = get_client()
    if not client:
        return []

    try:
        # Using the SDK pattern from the screenshot
        response = client.search.execute(q=query, limit=limit)
        # The screenshot shows `print(response.results)`
        return response.results
    except Exception as e:
        print(f"Error querying memory with SDK: {e}")
        return []
