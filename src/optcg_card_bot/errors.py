from __future__ import annotations


class BotError(Exception):
    user_message = "Something went wrong. Please try again."


class PoneglyphError(BotError):
    user_message = "Poneglyph is unavailable right now. Please try again soon."


class PoneglyphValidationError(PoneglyphError):
    user_message = "Poneglyph could not understand that query."


class PoneglyphNotFoundError(PoneglyphError):
    user_message = "No matching card was found."


class PoneglyphRateLimitError(PoneglyphError):
    user_message = "Poneglyph is rate-limiting requests. Please try again soon."


class PoneglyphServerError(PoneglyphError):
    user_message = "Poneglyph returned a temporary server error."


class PoneglyphNetworkError(PoneglyphError):
    user_message = "Could not reach Poneglyph. Please try again soon."


class NoSearchResultsError(BotError):
    user_message = "No matching cards were found."
