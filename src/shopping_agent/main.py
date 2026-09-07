"""Command-line entry point for the stateful shopping-agent conversation."""

from __future__ import annotations

from shopping_agent.agent import ShoppingState, build_shopping_graph, initial_state


EXIT_COMMANDS = {"exit", "quit"}


def run() -> None:
    """Run the outer user <-> agent loop using the graph's mock services."""
    graph = build_shopping_graph()
    state: ShoppingState = initial_state()

    print("Shopping agent ready. Type 'exit' or 'quit' to leave.")
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
        state["last_user_message"] = user_message
        state["input_status"] = "uninterpreted"
        state["awaiting_user_input"] = False
        state = graph.invoke(state)

        if response := state.get("assistant_message"):
            print(f"Agent: {response}")


if __name__ == "__main__":
    run()
