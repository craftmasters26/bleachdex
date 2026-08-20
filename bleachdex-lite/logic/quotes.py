"""
Flavor text shown above a spawn, in the spirit of Bleach. These are
original lines written in the tone of the series, not verbatim quotes
pulled from the show/manga - keeps things flavorful without needing to
reproduce copyrighted dialogue.
"""

import random

SPAWN_QUOTES = [
    "If you don't catch me, somebody else will.",
    "A blade left undrawn cuts no one — draw quickly.",
    "Even the weakest soul can seize a chance like this.",
    "This reiatsu won't linger in the world of the living for long.",
    "Hesitation is a soul reaper's worst enemy. Move.",
    "The Soul Society doesn't wait for the slow.",
    "Somewhere, a hollow is laughing at your indecision.",
    "Bankai isn't the only thing that takes a split second to lose.",
    "Every soul reaper in Karakura Town just felt this appear.",
    "Speed isn't everything — but right now, it's the only thing.",
]


def random_spawn_quote() -> str:
    return random.choice(SPAWN_QUOTES)


# Shown (publicly, mentioning the guesser) when someone's guess is wrong.
# Bleach-flavored ribbing only - never generic insults.
ROAST_QUOTES = [
    "Even Kon could've guessed that one, {user}.",
    "That guess had less bite than Zangetsu's blunt side, {user}.",
    "Yamamoto retired faster than your brain just worked, {user}.",
    "Even a Hollow with half a mask could've named that, {user}.",
    "Chad talks more than that guess made sense, {user}.",
    "Your reiatsu for guessing is Academy Year One at best, {user}.",
    "Ganju could rebuild a whole railway faster than you got that right, {user}.",
    "Even Rukia's terrible drawings are more recognizable than that guess, {user}.",
    "That was weaker than Ichigo's excuses for skipping class, {user}.",
    "Nice try, but even Keigo saw that one coming - and missed too, {user}.",
    "This wasn't part of Aizen's plan, {user}.",
]

# Shown (publicly, mentioning the winner) when someone catches a spawn.
CONGRATS_QUOTES = [
    "Bankai-level instincts, {user}. Nicely caught.",
    "Sharp eyes, {user} - Soul Society would be proud.",
    "That catch had more precision than a Quincy's arrow, {user}.",
    "{user} moved like flash step itself. Well caught.",
    "Not even a Hollow could've snatched that one from you, {user}.",
    "Reiatsu well spent, {user}. That one's yours now.",
    "Captain-level reflexes right there, {user}.",
    "{user} caught it clean - Zangetsu would approve.",
]


def random_roast_quote(user_mention: str) -> str:
    return random.choice(ROAST_QUOTES).format(user=user_mention)


def random_congrats_quote(user_mention: str) -> str:
    return random.choice(CONGRATS_QUOTES).format(user=user_mention)
