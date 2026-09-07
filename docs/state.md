## `ShoppingState`

Conversation state is explicit rather than inferred from loosely related booleans:

- `input_status`: whether the latest message is still raw (`uninterpreted`) or has passed through the LLM.
- `requirements`: stated product facts and preferences, including `no_preference_fields` for values such as “any brand is fine”.
- `requirement_status`, `missing_required_information`, and `optional_preferences`: the LLM's per-request judgement of search readiness. A brand is not required unless the LLM determines it is needed for that request.
- `search_required`, `search_completed`, and `search_result_status`, plus the raw and qualified product collections.
- `review_status`, `ranking_status`, and `presentation_status`: small lifecycle enums that make the next operation unambiguous.
- `purchase_status` and `selected_product_id`: purchase intent and outcome without overloading display state.
- `awaiting_user_input` and `finished`: terminal/wait guards that prevent the graph from looping after a question, result page, cart action, or termination.
