import asyncio
import json
from pathlib import Path

import pytest

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind
from optcg_card_bot.errors import PoneglyphRateLimitError
from optcg_card_bot.interactions import (
    CardSelectView,
    SearchResultsView,
    autocomplete_card_choices,
    build_choice_options,
    create_bot,
    prepare_bracket_queries,
    send_error,
    send_outcome,
)
from optcg_card_bot.models import CardDetailResponse, PricePoint
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
        self.edits: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] = []

    async def defer(self, **kwargs: object) -> None:
        self.defers.append(kwargs)

    async def edit_message(self, **kwargs: object) -> None:
        self.edits.append(kwargs)

    async def send_message(self, *args: object, **kwargs: object) -> None:
        self.messages.append({"args": args, **kwargs})


class FakeUser:
    def __init__(self, user_id: int = 123) -> None:
        self.id = user_id


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
        self.faq_queries: list[str] = []
        self.price_calls: list[tuple[str, int]] = []

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

    async def faq(self, query: str) -> CommandOutcome:
        self.faq_queries.append(query)
        if self.outcome is None:
            raise PoneglyphRateLimitError
        return self.outcome

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

    async def price(self, query: str, *, days: int = 30) -> CommandOutcome:
        self.price_calls.append((query, days))
        if self.outcome is None:
            raise PoneglyphRateLimitError
        return self.outcome


class BlockingSearchService(FakeService):
    def __init__(self, outcome: CommandOutcome) -> None:
        super().__init__(outcome)
        self.search_started = asyncio.Event()
        self.allow_search = asyncio.Event()

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
        self.search_started.set()
        await self.allow_search.wait()
        if self.outcome is None:
            raise PoneglyphRateLimitError
        return self.outcome


def load_card():
    return CardDetailResponse.model_validate(
        json.loads((FIXTURES / "card_op01_001.json").read_text())
    ).data


def load_price() -> PricePoint:
    return PricePoint(
        variant_index=0,
        label="Super Pre-Release",
        sub_type="Alternate Art",
        tcgplayer_url="https://tcgplayer.example/op01-001",
        market_price="1.91",
        low_price="1.00",
        mid_price="2.25",
        high_price="9.99",
        fetched_at="2026-06-04T12:00:00.000Z",
    )


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


def test_search_results_view_has_navigation_buttons() -> None:
    view = SearchResultsView(
        owner_id=123,
        source_query="luffy",
        page=1,
        total=30,
        has_more=True,
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
        service=FakeService(),
    )

    buttons = {
        item.label: item
        for item in view.children
        if item.__class__.__name__ == "SearchPageButton"
    }

    assert view.page == 1
    assert view.total == 30
    assert buttons["Previous"].disabled is True
    assert buttons["Next"].disabled is False

    last_page_view = SearchResultsView(
        owner_id=123,
        source_query="luffy",
        page=2,
        total=30,
        has_more=False,
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
        service=FakeService(),
    )
    last_page_buttons = {
        item.label: item
        for item in last_page_view.children
        if item.__class__.__name__ == "SearchPageButton"
    }

    assert last_page_buttons["Previous"].disabled is False
    assert last_page_buttons["Next"].disabled is True


def test_create_bot_registers_expected_commands() -> None:
    bot = create_bot(command_service=None)

    names = {command.name for command in bot.tree.get_commands()}

    assert {"card", "search", "random", "faq", "price", "help"} <= names


def test_create_bot_registers_price_command() -> None:
    bot = create_bot(command_service=None)

    command = bot.tree.get_command("price")

    assert command is not None
    assert {param.name for param in command.parameters} == {"card", "days"}


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
async def test_public_price_outcome_after_private_defer_uses_channel_send() -> None:
    interaction = FakeInteraction()
    outcome = CommandOutcome(
        kind=CommandOutcomeKind.PUBLIC_PRICE,
        card=load_card(),
        prices=(load_price(),),
    )

    await send_outcome(interaction, outcome, public_channel=True)

    assert len(interaction.channel.sends) == 1
    assert "embed" in interaction.channel.sends[0]
    assert interaction.deleted_original_response is True
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
async def test_card_and_faq_ambiguous_commands_use_card_select_view() -> None:
    choices = (
        CardChoice(
            card_number="OP01-001",
            name="Roronoa Zoro",
            set_code="OP01",
            card_type="Leader",
            color=("Red",),
        ),
    )
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Select a card",
            choices=choices,
        )
    )
    bot = create_bot(command_service=service)
    card_command = bot.tree.get_command("card")
    faq_command = bot.tree.get_command("faq")
    assert card_command is not None
    assert faq_command is not None
    card_interaction = FakeInteraction()
    faq_interaction = FakeInteraction()

    await card_command.callback(card_interaction, "luffy")
    await faq_command.callback(faq_interaction, "luffy")

    assert type(card_interaction.followup.sends[0]["view"]) is CardSelectView
    assert type(faq_interaction.followup.sends[0]["view"]) is CardSelectView
    assert service.queries == ["luffy"]
    assert service.faq_queries == ["luffy"]


@pytest.mark.asyncio
async def test_search_command_sends_search_results_view() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Search results | Page 1 | 30 total",
            choices=(
                CardChoice(
                    card_number="OP01-001",
                    name="Roronoa Zoro",
                    set_code="OP01",
                    card_type="Leader",
                    color=("Red",),
                ),
            ),
            source_query="type:leader",
            page=1,
            total=30,
            has_more=True,
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
    assert interaction.followup.sends[0]["args"] == (
        "Search results | Page 1 | 30 total",
    )
    assert isinstance(interaction.followup.sends[0]["view"], SearchResultsView)
    assert interaction.followup.sends[0]["ephemeral"] is True


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
async def test_search_results_next_callback_updates_page() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Search results | Page 3 | 30 total",
            choices=(
                CardChoice(
                    card_number="OP01-001",
                    name="Roronoa Zoro",
                    set_code="OP01",
                    card_type="Leader",
                    color=("Red",),
                ),
            ),
            source_query="luffy",
            page=3,
            total=30,
            has_more=False,
        )
    )
    view = SearchResultsView(
        owner_id=123,
        source_query="luffy",
        page=2,
        total=30,
        has_more=True,
        choices=service.outcome.choices,
        service=service,
    )
    next_button = next(
        item for item in view.children if getattr(item, "label", None) == "Next"
    )

    await next_button.callback(interaction)

    assert service.search_calls == [
        {
            "query": "luffy",
            "page": 3,
            "sort": None,
            "order": None,
        }
    ]
    assert interaction.response.defers == [{"thinking": False}]
    assert interaction.response.edits == []
    assert interaction.edits[0]["content"] == "Search results | Page 3 | 30 total"
    assert isinstance(interaction.edits[0]["view"], SearchResultsView)
    assert interaction.edits[0]["view"].page == 3


@pytest.mark.asyncio
async def test_search_results_next_callback_defers_before_search_completes() -> None:
    interaction = FakeInteraction()
    service = BlockingSearchService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Search results | Page 3 | 30 total",
            choices=(
                CardChoice(
                    card_number="OP01-001",
                    name="Roronoa Zoro",
                    set_code="OP01",
                    card_type="Leader",
                    color=("Red",),
                ),
            ),
            source_query="luffy",
            page=3,
            total=30,
            has_more=False,
        )
    )
    view = SearchResultsView(
        owner_id=123,
        source_query="luffy",
        page=2,
        total=30,
        has_more=True,
        choices=service.outcome.choices,
        service=service,
    )
    next_button = next(
        item for item in view.children if getattr(item, "label", None) == "Next"
    )

    task = asyncio.create_task(next_button.callback(interaction))
    await service.search_started.wait()

    try:
        assert interaction.response.defers == [{"thinking": False}]
    finally:
        service.allow_search.set()
        await task

    assert service.search_calls == [
        {
            "query": "luffy",
            "page": 3,
            "sort": None,
            "order": None,
        }
    ]
    assert interaction.response.edits == []
    assert interaction.edits[0]["content"] == "Search results | Page 3 | 30 total"
    assert isinstance(interaction.edits[0]["view"], SearchResultsView)
    assert interaction.edits[0]["view"].page == 3


@pytest.mark.asyncio
async def test_search_results_previous_callback_uses_previous_page() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Search results | Page 1 | 30 total",
            choices=(
                CardChoice(
                    card_number="OP01-001",
                    name="Roronoa Zoro",
                    set_code="OP01",
                    card_type="Leader",
                    color=("Red",),
                ),
            ),
            source_query="luffy",
            page=1,
            total=30,
            has_more=True,
        )
    )
    view = SearchResultsView(
        owner_id=123,
        source_query="luffy",
        page=2,
        total=30,
        has_more=True,
        choices=service.outcome.choices,
        service=service,
    )
    previous_button = next(
        item for item in view.children if getattr(item, "label", None) == "Previous"
    )

    await previous_button.callback(interaction)

    assert service.search_calls == [
        {
            "query": "luffy",
            "page": 1,
            "sort": None,
            "order": None,
        }
    ]
    assert interaction.response.defers == [{"thinking": False}]
    assert interaction.response.edits == []
    assert interaction.edits[0]["content"] == "Search results | Page 1 | 30 total"
    assert interaction.edits[0]["view"].page == 1


@pytest.mark.asyncio
async def test_search_results_buttons_only_allow_original_user() -> None:
    interaction = FakeInteraction()
    interaction.user = FakeUser(user_id=999)
    service = FakeService()
    view = SearchResultsView(
        owner_id=123,
        source_query="luffy",
        page=1,
        total=30,
        has_more=True,
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
        service=service,
    )
    next_button = next(
        item for item in view.children if getattr(item, "label", None) == "Next"
    )

    await next_button.callback(interaction)

    assert service.search_calls == []
    assert interaction.response.messages == [
        {
            "args": ("Only the command user can use this picker.",),
            "ephemeral": True,
        }
    ]


@pytest.mark.asyncio
async def test_price_command_posts_public_price_outcome_to_channel() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_PRICE,
            card=load_card(),
            prices=(load_price(),),
        )
    )
    bot = create_bot(command_service=service)
    command = bot.tree.get_command("price")
    assert command is not None

    await command.callback(interaction, "OP01-001", 14)

    assert service.price_calls == [("OP01-001", 14)]
    assert interaction.response.defers == [{"ephemeral": True}]
    assert len(interaction.channel.sends) == 1
    assert "embed" in interaction.channel.sends[0]
    assert interaction.deleted_original_response is True
    assert interaction.followup.sends == []


@pytest.mark.asyncio
async def test_price_command_ambiguous_uses_price_picker_action() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PICKER,
            message="Select a card for price history",
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
    command = bot.tree.get_command("price")
    assert command is not None

    await command.callback(interaction, "zoro", 7)

    assert interaction.followup.sends[0]["args"] == ("Select a card for price history",)
    view = interaction.followup.sends[0]["view"]
    assert isinstance(view, CardSelectView)
    assert view.action == "price"
    assert view.price_days == 7


@pytest.mark.asyncio
async def test_price_picker_selection_preserves_requested_days() -> None:
    interaction = FakeInteraction()
    service = FakeService(
        CommandOutcome(
            kind=CommandOutcomeKind.PUBLIC_PRICE,
            card=load_card(),
            prices=(load_price(),),
        )
    )
    view = CardSelectView(
        owner_id=123,
        source_query="zoro",
        action="price",
        choices=(
            CardChoice(
                card_number="OP01-001",
                name="Roronoa Zoro",
                set_code="OP01",
                card_type="Leader",
                color=("Red",),
            ),
        ),
        service=service,
        price_days=7,
    )
    select = view.children[0]
    select._values = ["OP01-001"]

    await select.callback(interaction)

    assert service.price_calls == [("OP01-001", 7)]
    assert len(interaction.followup.sends) == 1
    assert "embed" in interaction.followup.sends[0]


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
