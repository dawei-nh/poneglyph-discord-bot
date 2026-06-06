import json
from pathlib import Path

import pytest

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind
from optcg_card_bot.errors import PoneglyphRateLimitError
from optcg_card_bot.interactions import (
    CardSelectView,
    autocomplete_card_choices,
    build_choice_options,
    create_bot,
    prepare_bracket_queries,
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


class FakeMessageAuthor:
    def __init__(self, *, bot: bool) -> None:
        self.bot = bot


class FakeMessage:
    def __init__(self, *, content: str, author_bot: bool = False) -> None:
        self.author = FakeMessageAuthor(bot=author_bot)
        self.channel = FakeChannel()
        self.content = content


class FakeService:
    def __init__(self, outcome: CommandOutcome | None = None) -> None:
        self.outcome = outcome
        self.queries: list[str] = []
        self.autocomplete_queries: list[str] = []
        self.autocomplete_response: tuple[str, ...] = tuple(
            f"Card {index}" for index in range(30)
        )
        self.raise_on_autocomplete = False
        self.search_calls: list[dict[str, object]] = []

    async def card(self, query: str) -> CommandOutcome:
        self.queries.append(query)
        if self.outcome is None:
            raise PoneglyphRateLimitError
        return self.outcome

    async def autocomplete_cards(self, query: str) -> tuple[str, ...]:
        self.autocomplete_queries.append(query)
        if self.raise_on_autocomplete:
            raise PoneglyphRateLimitError
        return self.autocomplete_response

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        sort: str | None = None,
        order: str | None = None,
    ) -> CommandOutcome:
        self.search_calls.append(
            {
                "query": query,
                "page": page,
                "sort": sort,
                "order": order,
            }
        )
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


@pytest.mark.asyncio
async def test_autocomplete_card_choices_returns_capped_trimmed_choices() -> None:
    service = FakeService()
    service.autocomplete_response = ("Monkey.D.Luffy", "Roronoa Zoro" * 12) + tuple(
        f"Card {index}" for index in range(30)
    )

    choices = await autocomplete_card_choices(service, "luffy")

    truncated_long_choice = ("Roronoa Zoro" * 12)[:100]
    assert service.autocomplete_queries == ["luffy"]
    assert [(choice.name, choice.value) for choice in choices[:2]] == [
        ("Monkey.D.Luffy", "Monkey.D.Luffy"),
        (truncated_long_choice, truncated_long_choice),
    ]
    assert len(choices) == 25
    assert all(len(choice.name) <= 100 for choice in choices)
    assert all(len(choice.value) <= 100 for choice in choices)


@pytest.mark.asyncio
async def test_autocomplete_card_choices_returns_empty_choices_for_bot_error() -> None:
    service = FakeService()
    service.raise_on_autocomplete = True

    choices = await autocomplete_card_choices(service, "luffy")

    assert choices == []


def test_card_oriented_commands_have_poneglyph_autocomplete() -> None:
    bot = create_bot(command_service=FakeService())

    expected_params = {
        "card": "query",
        "search": "query",
        "random": "query",
        "faq": "card",
    }
    for command_name, parameter_name in expected_params.items():
        command = bot.tree.get_command(command_name)
        assert command is not None
        parameter = command.get_parameter(parameter_name)
        assert parameter is not None
        assert parameter.autocomplete is not None


def test_create_bot_can_enable_bracket_listener() -> None:
    bot = create_bot(command_service=None, enable_bracket_messages=True)

    assert "on_message" in bot.extra_events


def test_create_bot_only_enables_message_content_intent_for_brackets() -> None:
    default_bot = create_bot(command_service=None)
    bracket_bot = create_bot(command_service=None, enable_bracket_messages=True)

    assert default_bot.intents.message_content is False
    assert bracket_bot.intents.message_content is True


def test_prepare_bracket_queries_dedupes_and_caps() -> None:
    queries = prepare_bracket_queries("[[luffy]] [[luffy]] [[zoro]] [[nami]] [[sanji]]")

    assert queries == ("luffy", "zoro", "nami")


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
async def test_search_command_forwards_sort_and_order() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Search results",
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
    )
    bot = create_bot(command_service=service)
    command = bot.tree.get_command("search")
    assert command is not None

    await command.callback(interaction, "type:leader", "market_price", "desc")

    assert interaction.response.defers == [{"ephemeral": True}]
    assert service.search_calls == [
        {
            "query": "type:leader",
            "page": 1,
            "sort": "market_price",
            "order": "desc",
        }
    ]
    assert len(interaction.followup.sends) == 1


def test_search_command_registers_sort_and_order_choices() -> None:
    bot = create_bot(command_service=None)
    command = bot.tree.get_command("search")
    assert command is not None

    params = {parameter.name: parameter for parameter in command.parameters}

    assert [choice.value for choice in params["sort"].choices] == [
        "relevance",
        "card_number",
        "name",
        "cost",
        "power",
        "market_price",
        "released",
        "rarity",
        "color",
        "artist",
        "number",
        "set",
        "usd",
    ]
    assert [choice.value for choice in params["order"].choices] == ["asc", "desc"]
    assert params["sort"].required is False
    assert params["order"].required is False


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
async def test_bracket_listener_ignores_bot_authors() -> None:
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_CARD,
            card=load_card(),
        )
    )
    bot = create_bot(command_service=service, enable_bracket_messages=True)
    listener = bot.extra_events["on_message"][0]
    message = FakeMessage(content="[[OP01-001]]", author_bot=True)

    await listener(message)

    assert service.queries == []
    assert message.channel.sends == []


@pytest.mark.asyncio
async def test_bracket_listener_sends_public_card_embed() -> None:
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_CARD,
            card=load_card(),
        )
    )
    bot = create_bot(command_service=service, enable_bracket_messages=True)
    listener = bot.extra_events["on_message"][0]
    message = FakeMessage(content="[[OP01-001]]")

    await listener(message)

    assert service.queries == ["OP01-001"]
    assert len(message.channel.sends) == 1
    assert "embed" in message.channel.sends[0]


@pytest.mark.asyncio
async def test_bot_setup_hook_syncs_command_tree(monkeypatch) -> None:
    bot = create_bot(command_service=None)
    calls: list[str] = []

    async def fake_sync() -> None:
        calls.append("sync")

    monkeypatch.setattr(bot.tree, "sync", fake_sync)

    await bot.setup_hook()

    assert calls == ["sync"]
