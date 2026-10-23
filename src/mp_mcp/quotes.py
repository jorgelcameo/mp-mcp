"""The initial, intentionally small Max Payne quote corpus."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    id: str
    text: str
    speaker: str
    source: str


# The page's existing Monologues lines are attributed to Max Payne. The Lupino
# entry is the example supplied for this feature. Add verified entries here as
# the v1 corpus grows; the matcher may select IDs but never invent quote text.
QUOTES = (
    Quote(
        id="lupino-fallen-angels",
        text="The flesh of fallen angels!",
        speaker="Jack Lupino",
        source="User-provided example",
    ),
    Quote(
        id="max-wife-and-child",
        text="My wife and child were dead. I had nothing left except a gun and a bad habit.",
        speaker="Max Payne",
        source="Website Monologues",
    ),
    Quote(
        id="max-cold-business",
        text="It was a cold business, and I was the best there was at it.",
        speaker="Max Payne",
        source="Website Monologues",
    ),
    Quote(
        id="max-painkillers",
        text="Painkillers kept me sane. The world kept trying to take that away.",
        speaker="Max Payne",
        source="Website Monologues",
    ),
    Quote(
        id="max-twin-moons",
        text="The twin moons of my bloody past hung low and huge in the sky.",
        speaker="Max Payne",
        source="Website Monologues",
    ),
    Quote(
        id="max-dream-of-wife",
        text=(
            "I had a dream of my wife. She was pregnant, and I was scared. "
            "It was a good dream. Then I woke up."
        ),
        speaker="Max Payne",
        source="Website Monologues",
    ),
    Quote(
        id="vinnie-baseball-bat-boy",
        text="Those are priceless collectors items!",
        speaker="Vinnie Gognitti",
        source="Max Payne 2: The Fall of Max Payne — Captain Baseball Bat Boy scene",
    ),
    Quote(
        id="mona-bastard",
        text="You're a bastard, Max.",
        speaker="Mona Sax",
        source="Max Payne 2: The Fall of Max Payne",
    ),
    Quote(
        id="vlad-catchphrase",
        text="Have no fear, Vlad is here!",
        speaker="Vladimir Lem",
        source="Max Payne 2: The Fall of Max Payne",
    ),
    Quote(
        id="v-junkie-end-of-world",
        text="It's the end of the world as we know it.",
        speaker="V-junkie 2",
        source="Max Payne",
    ),
    Quote(
        id="mona-damsel-distress",
        text="God! I turned out to be a damsel in distress.",
        speaker="Mona Sax",
        source="Max Payne 2: The Fall of Max Payne",
    ),
    Quote(
        id="address-unknown",
        text="Mirrors are more fun than television.",
        speaker="John Mirra",
        source="Max Payne 2: The Fall of Max Payne",
    ),
    Quote(
        id="max-payne-ending",
        text="They were all dead. The final gunshot was an exclamation mark to everything that had led to this point. I released my finger from the trigger, and it was over.",
        speaker="Max Payne",
        source="Max Payne 2: The Fall of Max Payne",
    ),
    Quote(
        id="binary-choice",
        text="Pulling the gun is a binary choice. You either do it or you don't.",
        speaker="Max Payne",
        source="Max Payne 2: The Fall of Max Payne",
    ),
    Quote(
        id="max-genius-hole",
        text="The genius of the hole: no matter how long you spend climbing out, you can still fall back down in an instant.",
        speaker="Max Payne",
        source="Max Payne 2: The Fall of Max Payne",
    )
)

QUOTES_BY_ID = {quote.id: quote for quote in QUOTES}
