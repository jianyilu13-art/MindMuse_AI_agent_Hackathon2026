# State lifecycle

Each user turn follows this lifecycle:

1. `interpret_user_input` classifies the message.
2. `extract_requirements` asks Groq for the category and category-specific
   attribute proposals, then merges the new values with earlier turns.
3. `ask_clarification` presents required and optional attributes when a
   required value is missing.
4. `search_products` converts the requirements into `ShoppingToolInput` and
   calls the search tool once.
5. Reviews, ranking, and presentation run only after a successful search.

The outer CLI and browser UI reset `input_status` to `uninterpreted` before
every new turn. This is what lets a reply such as `size 37` continue the same
conversation after the agent has asked for a missing attribute.
