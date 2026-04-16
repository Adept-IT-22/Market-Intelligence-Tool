from agent_manager import AgentManager

def test_workplace_query():
    query = "Who is the most qualified worker for the 'Plexus Energy' project based on their skills?"
    print(f"Executing Test Query: {query}")
    
    agent = AgentManager(query=query)
    response = agent.pipeline()
    
    print("\n--- AGENT RESPONSE ---")
    print(response)
    print("----------------------")

if __name__ == "__main__":
    test_workplace_query()
