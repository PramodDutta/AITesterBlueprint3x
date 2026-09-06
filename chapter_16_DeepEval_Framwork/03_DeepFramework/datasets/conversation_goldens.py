"""Multi-turn conversations for the conversational metrics.

Single-turn metrics cannot see the failure these catch: a bot that answers
each message correctly but forgets what the user told it two turns ago.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversationGolden:
    name: str
    user_turns: list[str]
    # What the user established early that the bot must still honour later.
    retained_fact: str = ""
    categories: list[str] = field(default_factory=list)


CONVERSATION_GOLDENS: list[ConversationGolden] = [
    ConversationGolden(
        name="Refund inside the window",
        user_turns=[
            "Hi, I bought a hoodie 12 days ago and it does not fit.",
            "Can I still return it?",
            "How long until the money is back on my card?",
        ],
        retained_fact="The order was placed 12 days ago, inside the 30-day window.",
        categories=["return", "refund"],
    ),
    ConversationGolden(
        name="Shipping upgrade mid-conversation",
        user_turns=[
            "I am ordering the LED desk lamp today.",
            "My order total is $39. Do I get free shipping?",
            "What if I want it in 2 days instead?",
        ],
        retained_fact="The cart total is $39, which is under the $50 free-shipping threshold.",
        categories=["shipping"],
    ),
    ConversationGolden(
        name="Out of scope then back in scope",
        user_turns=[
            "Can I pay with cryptocurrency?",
            "Okay, then how do I reset my password?",
        ],
        retained_fact="Crypto is out of scope; the bot must not invent a payment policy.",
        categories=["account", "out_of_scope"],
    ),
]
