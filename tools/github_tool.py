from github import Github

def list_repos(access_token: str):
    """
    Lists the authenticated user's repositories.
    """
    try:
        g = Github(access_token)
        user = g.get_user()
        print(f"DEBUG: Listing repos for user: {user.login}")
        
        repos = user.get_repos(sort="updated", direction="desc")
        results = []
        for r in repos:
            results.append({
                "name": r.name,
                "url": r.html_url,
                "description": r.description,
                "stars": r.stargazers_count,
                "language": r.language
            })
        return results
    except Exception as e:
        print(f"DEBUG: list_repos exception: {e}")
        return f"Error listing GitHub repos: {str(e)}"

def search_repos(access_token: str, query: str):
    """
    Searches for repositories on GitHub.
    """
    try:
        g = Github(access_token)
        user = g.get_user()
        login = user.login
        
        print(f"DEBUG: Searching repos for user {login} with query: {query}")
        # Search within user's repos by default
        search_query = f"user:{login} {query}"
        repos = g.search_repositories(query=search_query)
        
        results = []
        for r in repos:
            results.append({
                "name": r.name,
                "url": r.html_url,
                "description": r.description,
                "stars": r.stargazers_count,
                "language": r.language
            })
        return results
    except Exception as e:
        print(f"DEBUG: search_repos exception: {e}")
        return f"Error searching GitHub repos: {str(e)}"
