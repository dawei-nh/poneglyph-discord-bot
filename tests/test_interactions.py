import json
from pathlib import Path

import pytest

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind
from optcg_card_bot.errors import PoneglyphRateLimitError
from optcg_card_bot.interactions import (
    CardSelectView,
    build_choice_options,
    create_bot,
    send_error,
    send_outcome,
)
from optcg_card_bot.models import CardDetailResponse
from optcg_card_bot.search import CardChoice

FIXTURES = Path(__file__).parent / "fixtures" / "poneglyph"


class FakeFollowup:
    def __init__(self) -> None:
        self.sends: list[dict[str, object]] = []

    async def send(self, *args: object, **kwargs: object) -> None:
        self.sends.append({"args": args, **kwargs})


class FakeChannel:
    def __init__(self) -> None:
        self.sends: list[dict[str, object]] = []

    async def send(self, *args: object, **kwargs: object) -> None:
        self.sends.append({"args": args, **kwargs})


class FakeInteraction:
    def __init__(self) -> None:
        self.followup = FakeFollowup()
        self.channel = FakeChannel()
        self.response = FakeResponse()
        self.user = FakeUser()
        self.deleted_original_response = False
        self.edits: list[dict[str, object]] = []

    async def delete_original_response(self) -> None:
        self.deleted_original_response = True

    async def edit_original_response(self, **kwargs: object) -> None:
        self.edits.append(kwargs)


class FakeInteractionWithoutDelete:
    def __init__(self) -> None:
        self.followup = FakeFollowup()
        self.channel = FakeChannel()
        self.edits: list[dict[str, object]] = []

    async def edit_original_response(self, **kwargs: object) -> None:
        self.edits.append(kwargs)


class FakeResponse:
    def __init__(self) -> None:
        self.defers: list[dict[str, object]] = []

    async def defer(self, **kwargs: object) -> None:
        self.defers.append(kwargs)


class FakeUser:
    id = 123


class FakeService:
    def __init__(self, outcome: CommandOutcome | None = None) -> None:
        self.outcome = outcome

    async def card(self, query: str) -> CommandOutcome:
        if self.outcome is None:
            raise PoneglyphRateLimitError
        return self.outcome


def load_card():
    return CardDetailResponse.model_validate(
        json.loads((FIXTURES / "card_op01_001.json").read_text())
    ).data


def test_choice_options_include_card_number_and_name() -> None:
    choices = (
        CardChoice(
            card_number="OP01-001",
            name="Roronoa Zoro",
            set_code="OP01",
            card_type="Leader",
            color=("Red",),
        ),
    )

    options = build_choice_options(choices)

    assert options[0].label == "Roronoa Zoro"
    assert options[0].value == "OP01-001"
    assert options[0].description == "OP01 • Leader • Red"


def test_select_view_tracks_owner_and_query() -> None:
    view = CardSelectView(
        owner_id=123,
        source_query="luffy",
        action="card",
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
    )

    assert view.owner_id == 123
    assert view.source_query == "luffy"
    assert view.action == "card"
    assert view.timeout == 180


def test_create_bot_registers_expected_commands() -> None:
    bot = create_bot(command_service=None)

    names = {command.name for command in bot.tree.get_commands()}

    assert {"card", "search", "random", "faq", "help"} <= names


def test_create_bot_can_enable_bracket_listener() -> None:
    bot = create_bot(command_service=None, enable_bracket_messages=True)

    assert "on_message" in bot.extra_events


@pytest.mark.asyncio
async def test_public_outcome_after_private_defer_uses_channel_send() -> None:
    interaction = FakeInteraction()
    outcome = CommandOutcome(
        kind=CommandOutcomeKind.PUBLIC_CARD,
        card=load_card(),
    )

    await send_outcome(interaction, outcome, public_channel=True)

    assert len(interaction.channel.sends) == 1
    assert "embed" in interaction.channel.sends[0]
    assert interaction.deleted_original_response is True
    assert interaction.edits == []
    assert interaction.followup.sends == []


@pytest.mark.asyncio
async def test_public_outcome_edits_original_response_when_delete_unavailable() -> None:
    interaction = FakeInteractionWithoutDelete()
    outcome = CommandOutcome(
        kind=CommandOutcomeKind.PUBLIC_CARD,
        card=load_card(),
    )

    await send_outcome(interaction, outcome, public_channel=True)

    assert len(interaction.channel.sends) == 1
    assert interaction.edits == [{"content": "Posted publicly.", "view": None}]
    assert interaction.followup.sends == []


@pytest.mark.asyncio
async def test_card_command_posts_direct_public_outcome_to_channel() -> None:
    interaction = FakeInteraction()
    bot = create_bot(
        command_service=FakeService(
            CommandOutcome(
                kind=CommandOutcomeKind.PUBLIC_CARD,
                card=load_card(),
            )
        )
    )
    command = bot.tree.get_command("card")
    assert command is not None

    await command.callback(interaction, "OP01-001")

    assert interaction.response.defers == [{"ephemeral": True}]
    assert len(interaction.channel.sends) == 1
    assert "embed" in interaction.channel.sends[0]
    assert interaction.deleted_original_response is True
    assert interaction.followup.sends == []


@pytest.mark.asyncio
async def test_bot_error_sends_user_message_ephemerally() -> None:
    interaction = FakeInteraction()

    await send_error(interaction, PoneglyphRateLimitError())

    assert interaction.followup.sends == [
        {
            "args": ("Poneglyph is rate-limiting requests. Please try again soon.",),
            "ephemeral": True,
        }
    ]


@pytest.mark.asyncio
async def test_card_command_bot_error_sends_user_message_ephemerally() -> None:
    interaction = FakeInteraction()
    bot = create_bot(command_service=FakeService())
    command = bot.tree.get_command("card")
    assert command is not None

    await command.callback(interaction, "OP01-001")

    assert interaction.response.defers == [{"ephemeral": True}]
    assert interaction.followup.sends == [
        {
            "args": ("Poneglyph is rate-limiting requests. Please try again soon.",),
            "ephemeral": True,
        }
    ]
    assert interaction.channel.sends == []


@pytest.mark.asyncio
async def test_bot_setup_hook_syncs_command_tree(monkeypatch) -> None:
    bot = create_bot(command_service=None)
    calls: list[str] = []

    async def fake_sync() -> None:
        calls.append("sync")

    monkeypatch.setattr(bot.tree, "sync", fake_sync)

    await bot.setup_hook()

    assert calls == ["sync"]
