"""Command-line entry point for the stateful shopping-agent conversation."""

from __future__ import annotations

import os

from shopping_agent.agent import ShoppingState, build_shopping_graph, initial_state


EXIT_COMMANDS = {"exit", "quit"}
WELCOME_MESSAGE = (
    "Hi! I’m Muse, your shopping assistant. What are you looking to buy?\n"
    "Tell me the product first; I’ll suggest the required and optional "
    "details that can improve the search. Type 'quit' or 'exit' anytime to "
    "leave."
)


def run() -> None:
    """Run the outer user <-> agent loop."""
    graph = build_shopping_graph()
    state: ShoppingState = initial_state()

    if os.getenv("GROQ_API_KEY"):
        print("Shopping agent ready — Groq is connected.")
    else:
        print(
            "Shopping agent ready — running local demo semantics. "
            "Set GROQ_API_KEY to use Groq."
        )

    print(WELCOME_MESSAGE)
    while not state["finished"]:
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_message:
            continue
        if user_message.lower() in EXIT_COMMANDS:
            print("Goodbye!")
            break

        # The graph receives the complete prior state plus only the new turn.
        # Reset the turn markers after a clarification/result response so the
        # router actually interprets the next user message.
        state.update(
            {
                "last_user_message": user_message,
                "input_status": "uninterpreted",
                "awaiting_user_input": False,
                "assistant_message": None,
                "last_error": None,
            }
        )
        state = graph.invoke(state)

        if response := state.get("assistant_message"):
            print(f"Agent: {response}")


if __name__ == "__main__":
    run()
