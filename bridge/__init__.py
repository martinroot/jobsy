"""Jobsy bridge: orders (freelance exchange) <-> agents (Dagi core).

Each order is a chat. A chat loads an agent from a template and the agent
works on the order using tools, streaming events back to the chat until
delivery.
"""
