from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.abc import Messageable
from discord.ext import commands

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind, CommandService
from optcg_card_bot.embeds import build_card_embed, build_faq_embed
from optcg_card_bot.errors import BotError
from optcg_card_bot.search import CardChoice, extract_bracket_queries

MAX_BRACKET_LOOKUPS_PER_MESSAGE = 3
MAX_AUTOCOMPLETE_CHOICES = 25
DISCORD_CHOICE_VALUE_LIMIT = 100
SEARCH_SORT_VALUES = (
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
)
SEARCH_SORT_CHOICES = [
    app_commands.Choice(name=sort_value, value=sort_value)
    for sort_value in SEARCH_SORT_VALUES
]
SEARCH_ORDER_CHOICES = [
    app_commands.Choice(name="asc", value="asc"),
    app_commands.Choice(name="desc", value="desc"),
]


def build_choice_options(choices: tuple[CardChoice, ...]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=choice.name[:100],
            value=choice.card_number,
            description=_choice_description(choice),
        )
        for choice in choices[:25]
    ]


class CardSelect(discord.ui.Select[discord.ui.View]):
    def __init__(self, choices: tuple[CardChoice, ...]) -> None:
        super().__init__(
            placeholder="Select a card to post",
            min_values=1,
            max_values=1,
            options=build_choice_options(choices),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, CardSelectView):
            await interaction.response.send_message(
                "This picker is not available.",
                ephemeral=True,
            )
            return
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message(
                "Only the command user can use this picker.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False)
        if view.service is None:
            await interaction.followup.send("This picker has expired.", ephemeral=True)
            return

        card_number = self.values[0]
        if view.action == "faq":
            try:
                outcome = await view.service.faq(card_number)
            except BotError as error:
                await send_error(interaction, error)
                return
        else:
            try:
                outcome = await view.service.card(card_number)
            except BotError as error:
                await send_error(interaction, error)
                return
        await send_outcome(interaction, outcome)


class CardSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        source_query: str,
        action: str,
        choices: tuple[CardChoice, ...],
        service: CommandService | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.source_query = source_query
        self.action = action
        self.service = service
        self.add_item(CardSelect(choices))


class SearchPageButton(discord.ui.Button["SearchResultsView"]):
    def __init__(self, *, label: str, page_delta: int, disabled: bool) -> None:
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
        )
        self.page_delta = page_delta

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, SearchResultsView):
            await interaction.response.send_message(
                "This picker is not available.",
                ephemeral=True,
            )
            return
        await view.change_page(interaction, self.page_delta)


class SearchResultsView(CardSelectView):
    def __init__(
        self,
        *,
        owner_id: int,
        source_query: str,
        page: int,
        total: int,
        has_more: bool,
        choices: tuple[CardChoice, ...],
        service: CommandService | None = None,
    ) -> None:
        super().__init__(
            owner_id=owner_id,
            source_query=source_query,
            action="card",
            choices=choices,
            service=service,
        )
        self.page = page
        self.total = total
        self.has_more = has_more
        self.add_item(
            SearchPageButton(
                label="Previous",
                page_delta=-1,
                disabled=page <= 1,
            )
        )
        self.add_item(
            SearchPageButton(
                label="Next",
                page_delta=1,
                disabled=not has_more,
            )
        )

    async def change_page(
        self,
        interaction: discord.Interaction,
        page_delta: int,
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the command user can use this picker.",
                ephemeral=True,
            )
            return
        if self.service is None:
            await interaction.response.send_message(
                "This picker has expired.",
                ephemeral=True,
            )
            return

        try:
            outcome = await self.service.search(
                self.source_query,
                page=max(1, self.page + page_delta),
            )
        except BotError as error:
            await interaction.response.send_message(error.user_message, ephemeral=True)
            return

        if outcome.kind is not CommandOutcomeKind.PICKER:
            await interaction.response.edit_message(content=outcome.message, view=None)
            return

        await interaction.response.edit_message(
            content=outcome.message,
            view=SearchResultsView(
                owner_id=self.owner_id,
                source_query=self.source_query,
                page=outcome.page,
                total=outcome.total,
                has_more=outcome.has_more,
                choices=outcome.choices,
                service=self.service,
            ),
        )


async def send_outcome(
    interaction: discord.Interaction,
    outcome: CommandOutcome,
    *,
    public_channel: bool = False,
) -> None:
    if outcome.kind is CommandOutcomeKind.PUBLIC_CARD and outcome.card is not None:
        embed = build_card_embed(outcome.card)
        if public_channel and hasattr(interaction.channel, "send"):
            channel = cast("Messageable", interaction.channel)
            await channel.send(embed=embed)
            await _clear_original_response(interaction)
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)
        return
    if outcome.kind is CommandOutcomeKind.PUBLIC_FAQ and outcome.card is not None:
        embed = build_faq_embed(outcome.card, outcome.faq_entries)
        if public_channel and hasattr(interaction.channel, "send"):
            channel = cast("Messageable", interaction.channel)
            await channel.send(embed=embed)
            await _clear_original_response(interaction)
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)
        return
    if outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE:
        await interaction.followup.send(outcome.message, ephemeral=True)
        return
    await interaction.followup.send("No response was produced.", ephemeral=True)


async def send_error(interaction: discord.Interaction, error: BotError) -> None:
    await interaction.followup.send(error.user_message, ephemeral=True)


async def _clear_original_response(interaction: discord.Interaction) -> None:
    if hasattr(interaction, "delete_original_response"):
        await interaction.delete_original_response()
        return
    if hasattr(interaction, "edit_original_response"):
        await interaction.edit_original_response(content="Posted publicly.", view=None)


def prepare_bracket_queries(content: str) -> tuple[str, ...]:
    queries: list[str] = []
    seen: set[str] = set()
    for query in extract_bracket_queries(content):
        if query in seen:
            continue
        queries.append(query)
        seen.add(query)
        if len(queries) == MAX_BRACKET_LOOKUPS_PER_MESSAGE:
            break
    return tuple(queries)


def build_autocomplete_choices(
    values: tuple[str, ...],
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(
            name=value[:DISCORD_CHOICE_VALUE_LIMIT],
            value=value[:DISCORD_CHOICE_VALUE_LIMIT],
        )
        for value in values[:MAX_AUTOCOMPLETE_CHOICES]
    ]


async def autocomplete_card_choices(
    service: CommandService,
    current: str,
) -> list[app_commands.Choice[str]]:
    try:
        choices = await service.autocomplete_cards(current)
    except BotError:
        return []
    return build_autocomplete_choices(choices)


class SyncingBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.tree.sync()


def create_bot(
    command_service: CommandService | None,
    *,
    enable_bracket_messages: bool = False,
) -> commands.Bot:
    intents = discord.Intents.default()
    if enable_bracket_messages:
        intents.message_content = True
    bot = SyncingBot(command_prefix=commands.when_mentioned, intents=intents)

    async def autocomplete_cards(
        _interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        service = _require_service(command_service)
        return await autocomplete_card_choices(service, current)

    @bot.tree.command(name="card", description="Search and post a Poneglyph card")
    @app_commands.describe(query="Poneglyph query or card number")
    @app_commands.autocomplete(query=autocomplete_cards)
    async def card(interaction: discord.Interaction, query: str) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.card(query)
        except BotError as error:
            await send_error(interaction, error)
            return
        if outcome.kind is CommandOutcomeKind.PICKER:
            await interaction.followup.send(
                outcome.message,
                view=CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=query,
                    action="card",
                    choices=outcome.choices,
                    service=service,
                ),
                ephemeral=True,
            )
            return
        await send_outcome(interaction, outcome, public_channel=True)

    @bot.tree.command(name="search", description="Browse Poneglyph search results")
    @app_commands.describe(
        query="Poneglyph query",
        sort="Optional Poneglyph sort field",
        order="Optional Poneglyph sort order",
    )
    @app_commands.choices(sort=SEARCH_SORT_CHOICES, order=SEARCH_ORDER_CHOICES)
    @app_commands.autocomplete(query=autocomplete_cards)
    async def search(
        interaction: discord.Interaction,
        query: str,
        sort: str | None = None,
        order: str | None = None,
    ) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.search(query, sort=sort, order=order)
        except BotError as error:
            await send_error(interaction, error)
            return
        if outcome.kind is CommandOutcomeKind.PICKER:
            await interaction.followup.send(
                outcome.message,
                view=SearchResultsView(
                    owner_id=interaction.user.id,
                    source_query=query,
                    page=outcome.page,
                    total=outcome.total,
                    has_more=outcome.has_more,
                    choices=outcome.choices,
                    service=service,
                ),
                ephemeral=True,
            )
            return
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="random", description="Post a random Poneglyph card")
    @app_commands.describe(query="Optional Poneglyph query or simple random filters")
    @app_commands.autocomplete(query=autocomplete_cards)
    async def random_card(interaction: discord.Interaction, query: str = "") -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=False)
        try:
            outcome = await service.random(query)
        except BotError as error:
            await send_error(interaction, error)
            return
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="faq", description="Post official FAQ for a card")
    @app_commands.describe(card="Card number or Poneglyph query")
    @app_commands.autocomplete(card=autocomplete_cards)
    async def faq(interaction: discord.Interaction, card: str) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.faq(card)
        except BotError as error:
            await send_error(interaction, error)
            return
        if outcome.kind is CommandOutcomeKind.PICKER:
            await interaction.followup.send(
                outcome.message,
                view=CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=card,
                    action="faq",
                    choices=outcome.choices,
                    service=service,
                ),
                ephemeral=True,
            )
            return
        await send_outcome(interaction, outcome, public_channel=True)

    @bot.tree.command(name="help", description="Show bot help")
    async def help_command(interaction: discord.Interaction) -> None:
        service = _require_service(command_service)
        await interaction.response.send_message(service.help().message, ephemeral=True)

    _registered_commands = (card, search, random_card, faq, help_command)
    if enable_bracket_messages:

        @bot.listen("on_message")
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            service = _require_service(command_service)
            for query in prepare_bracket_queries(message.content):
                try:
                    outcome = await service.card(query)
                except BotError as error:
                    await message.channel.send(error.user_message)
                    continue
                if outcome.kind is CommandOutcomeKind.PUBLIC_CARD and outcome.card:
                    await message.channel.send(embed=build_card_embed(outcome.card))
                elif outcome.kind is CommandOutcomeKind.PICKER:
                    await message.channel.send(
                        f"`[[{query}]]` matched multiple cards. Use `/card` to choose."
                    )
                elif outcome.message:
                    await message.channel.send(outcome.message)

        _registered_events = (on_message,)

    return bot


def _choice_description(choice: CardChoice) -> str:
    parts = [choice.set_code, choice.card_type]
    if choice.color:
        parts.append("/".join(choice.color))
    return " • ".join(parts)[:100]


def _require_service(service: CommandService | None) -> CommandService:
    if service is None:
        raise RuntimeError("CommandService is required for runtime command handling")
    return service
