from __future__ import annotations

from typing import Protocol, cast

import discord
from discord import app_commands
from discord.abc import Messageable
from discord.ext import commands

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind, CommandService
from optcg_card_bot.embeds import (
    CardEmbedMode,
    build_card_embed,
    build_faq_embed,
    build_price_embed,
    normalize_card_embed_mode,
)
from optcg_card_bot.errors import BotError
from optcg_card_bot.models import (
    CardDetail,
    VariantRequest,
    resolve_variant_position,
)
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
CARD_DISPLAY_CHOICES = [
    app_commands.Choice(name=mode.value, value=mode.value) for mode in CardEmbedMode
]

PICKER_EXPIRED_MESSAGE = "This picker expired. Run the command again."
MISSING_CHANNEL_ACCESS_MESSAGE = (
    "I couldn't post publicly in this channel. "
    "Check that the bot can view and send messages here."
)
BRACKET_FIRST_MATCH_NOTE = (
    "`[[{query}]]` matched multiple cards; "
    "showing the first result and may be incorrect."
)

VARIANT_CONTROLS_MESSAGE = (
    "Variant image controls\nOnly you can see this. Updates the public card embed."
)


class EditableMessage(Protocol):
    async def edit(
        self,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> object: ...


def build_choice_options(choices: tuple[CardChoice, ...]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=choice.name[:100],
            value=choice.card_number,
            description=_choice_description(choice),
        )
        for choice in choices[:25]
    ]


class VariantImageButton(discord.ui.Button["VariantImageView"]):
    def __init__(self, *, label: str, variant_delta: int) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.variant_delta = variant_delta

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, VariantImageView):
            await interaction.response.send_message(
                "Variant controls are not available.",
                ephemeral=True,
            )
            return
        await view.change_variant(interaction, self.variant_delta)


class VariantImageView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        card: CardDetail,
        variant_position: VariantRequest = 0,
        display_mode: CardEmbedMode | str = CardEmbedMode.SUMMARY,
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.card = card
        self.variant_position = resolve_variant_position(card, variant_position)
        self.display_mode = normalize_card_embed_mode(display_mode)
        self._public_message: EditableMessage | None = None
        self._control_message: EditableMessage | None = None
        self.add_item(VariantImageButton(label="Previous", variant_delta=-1))
        self.add_item(VariantImageButton(label="Next", variant_delta=1))

    def bind_public_message(self, message: EditableMessage | None) -> None:
        self._public_message = message

    def bind_control_message(self, message: EditableMessage | None) -> None:
        self._control_message = message

    async def change_variant(
        self,
        interaction: discord.Interaction,
        variant_delta: int,
    ) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the command user can cycle variants.",
                ephemeral=True,
            )
            return
        if len(self.card.variants) <= 1:
            await interaction.response.send_message(
                "This card has no alternate variant images.",
                ephemeral=True,
            )
            return
        if self._public_message is None:
            await interaction.response.send_message(
                "Variant controls expired.",
                ephemeral=True,
            )
            return

        self.variant_position = (self.variant_position + variant_delta) % len(
            self.card.variants
        )
        try:
            await self._public_message.edit(
                embed=build_card_embed(
                    self.card,
                    variant_position=self.variant_position,
                    display_mode=self.display_mode,
                )
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "I couldn't update the public card message.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            content=_variant_controls_message(self.card, self.variant_position),
            view=self,
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button | discord.ui.Select):
                item.disabled = True
        if self._control_message is None:
            return
        try:
            await self._control_message.edit(
                content=(
                    f"{_variant_controls_message(self.card, self.variant_position)}\n"
                    "Controls expired."
                ),
                view=self,
            )
        except discord.HTTPException:
            return


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
        try:
            if view.action == "faq":
                outcome = await view.service.faq(card_number)
            elif view.action == "price":
                outcome = await view.service.price(card_number, days=view.price_days)
            else:
                outcome = await view.service.card(card_number)
        except BotError as error:
            await send_error(interaction, error)
            return
        await send_outcome(
            interaction,
            outcome,
            public_channel=True,
            variant_position=view.variant_position,
            display_mode=view.display_mode,
        )


class CardSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        source_query: str,
        action: str,
        choices: tuple[CardChoice, ...],
        service: CommandService | None = None,
        price_days: int = 30,
        variant_position: VariantRequest = 0,
        display_mode: CardEmbedMode | str = CardEmbedMode.SUMMARY,
    ) -> None:
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.source_query = source_query
        self.action = action
        self.service = service
        self.price_days = price_days
        self.variant_position = variant_position
        self.display_mode = normalize_card_embed_mode(display_mode)
        self._message: EditableMessage | None = None
        self.add_item(CardSelect(choices))

    def bind_message(self, message: EditableMessage | None) -> None:
        self._message = message

    async def on_timeout(self) -> None:
        self.service = None
        for item in self.children:
            if isinstance(item, discord.ui.Button | discord.ui.Select):
                item.disabled = True
        if self._message is None:
            return
        try:
            await self._message.edit(content=PICKER_EXPIRED_MESSAGE, view=self)
        except discord.HTTPException:
            return


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
        sort: str | None = None,
        order: str | None = None,
        variant_position: VariantRequest = 0,
        display_mode: CardEmbedMode | str = CardEmbedMode.SUMMARY,
    ) -> None:
        super().__init__(
            owner_id=owner_id,
            source_query=source_query,
            action="card",
            choices=choices,
            service=service,
            variant_position=variant_position,
            display_mode=display_mode,
        )
        self.page = page
        self.total = total
        self.has_more = has_more
        self.sort = sort
        self.order = order
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

        await interaction.response.defer(thinking=False)

        try:
            outcome = await self.service.search(
                self.source_query,
                page=max(1, self.page + page_delta),
                sort=self.sort,
                order=self.order,
            )
        except BotError as error:
            await interaction.followup.send(error.user_message, ephemeral=True)
            return

        if outcome.kind is not CommandOutcomeKind.PICKER:
            await interaction.edit_original_response(content=outcome.message, view=None)
            self.bind_message(None)
            return

        next_view = SearchResultsView(
            owner_id=self.owner_id,
            source_query=self.source_query,
            page=outcome.page,
            total=outcome.total,
            has_more=outcome.has_more,
            choices=outcome.choices,
            service=self.service,
            sort=self.sort,
            order=self.order,
            variant_position=self.variant_position,
            display_mode=self.display_mode,
        )
        message = await interaction.edit_original_response(
            content=outcome.message,
            view=next_view,
        )
        next_view.bind_message(cast("EditableMessage | None", message))
        self.bind_message(None)


async def send_picker_followup(
    interaction: discord.Interaction,
    message: str,
    view: CardSelectView,
) -> None:
    sent_message = await interaction.followup.send(
        message,
        view=view,
        ephemeral=True,
        wait=True,
    )
    view.bind_message(cast("EditableMessage | None", sent_message))


def _variant_image_view(
    card: CardDetail,
    *,
    owner_id: int,
    variant_position: VariantRequest,
    display_mode: CardEmbedMode | str,
) -> VariantImageView | None:
    if len(card.variants) <= 1:
        return None
    return VariantImageView(
        owner_id=owner_id,
        card=card,
        variant_position=variant_position,
        display_mode=display_mode,
    )


def _variant_controls_message(card: CardDetail, variant_position: int) -> str:
    return (
        f"{VARIANT_CONTROLS_MESSAGE}\n"
        f"Current: Variant {variant_position + 1}/{len(card.variants)}"
    )


async def _send_variant_controls(
    interaction: discord.Interaction,
    view: VariantImageView,
    *,
    use_original_response: bool,
) -> None:
    content = _variant_controls_message(view.card, view.variant_position)
    if use_original_response and hasattr(interaction, "edit_original_response"):
        message = await interaction.edit_original_response(content=content, view=view)
        view.bind_control_message(cast("EditableMessage | None", message))
        return
    sent_message = await interaction.followup.send(
        content,
        view=view,
        ephemeral=True,
        wait=True,
    )
    view.bind_control_message(cast("EditableMessage | None", sent_message))


async def _send_public_embed(
    interaction: discord.Interaction,
    embed: discord.Embed,
    *,
    public_channel: bool,
    view: VariantImageView | None = None,
) -> None:
    if public_channel and hasattr(interaction.channel, "send"):
        channel = cast("Messageable", interaction.channel)
        try:
            sent_message = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(
                MISSING_CHANNEL_ACCESS_MESSAGE,
                ephemeral=True,
            )
            return
        if view is None:
            await _clear_original_response(interaction)
            return
        view.bind_public_message(cast("EditableMessage | None", sent_message))
        await _clear_original_response(interaction)
        await _send_variant_controls(
            interaction,
            view,
            use_original_response=False,
        )
        return
    if view is None:
        await interaction.followup.send(embed=embed, ephemeral=False)
        return
    sent_message = await interaction.followup.send(
        embed=embed,
        ephemeral=False,
        wait=True,
    )
    view.bind_public_message(cast("EditableMessage | None", sent_message))
    await _send_variant_controls(
        interaction,
        view,
        use_original_response=False,
    )


async def send_outcome(
    interaction: discord.Interaction,
    outcome: CommandOutcome,
    *,
    public_channel: bool = False,
    variant_position: VariantRequest = 0,
    display_mode: CardEmbedMode | str = CardEmbedMode.SUMMARY,
) -> None:
    if outcome.kind is CommandOutcomeKind.PUBLIC_CARD and outcome.card is not None:
        embed = build_card_embed(
            outcome.card,
            variant_position=variant_position,
            display_mode=display_mode,
        )
        await _send_public_embed(
            interaction,
            embed,
            public_channel=public_channel,
            view=_variant_image_view(
                outcome.card,
                owner_id=interaction.user.id,
                variant_position=variant_position,
                display_mode=display_mode,
            ),
        )
        return
    if outcome.kind is CommandOutcomeKind.PUBLIC_FAQ and outcome.card is not None:
        embed = build_faq_embed(outcome.card, outcome.faq_entries)
        await _send_public_embed(interaction, embed, public_channel=public_channel)
        return
    if outcome.kind is CommandOutcomeKind.PUBLIC_PRICE and outcome.card is not None:
        embed = build_price_embed(outcome.card, outcome.prices)
        await _send_public_embed(interaction, embed, public_channel=public_channel)
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
    @app_commands.describe(
        query="Poneglyph query or card number",
        variant="Variant index or name to show first; examples: 0, alt, sp, manga",
        display=(
            "Card embed detail level; summary is compact, detailed is current full view"
        ),
    )
    @app_commands.choices(display=CARD_DISPLAY_CHOICES)
    @app_commands.autocomplete(query=autocomplete_cards)
    async def card(
        interaction: discord.Interaction,
        query: str,
        variant: str = "",
        display: str = CardEmbedMode.SUMMARY.value,
    ) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.card(query)
        except BotError as error:
            await send_error(interaction, error)
            return
        if outcome.kind is CommandOutcomeKind.PICKER:
            await send_picker_followup(
                interaction,
                outcome.message,
                CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=query,
                    action="card",
                    choices=outcome.choices,
                    service=service,
                    variant_position=variant,
                    display_mode=display,
                ),
            )
            return
        await send_outcome(
            interaction,
            outcome,
            public_channel=True,
            variant_position=variant,
            display_mode=display,
        )

    @bot.tree.command(name="search", description="Browse Poneglyph search results")
    @app_commands.describe(
        query="Poneglyph query",
        sort="Optional Poneglyph sort field",
        order="Optional Poneglyph sort order",
        variant="Variant index or name to show first; examples: 0, alt, sp, manga",
        display="Card embed detail level for posted selections",
    )
    @app_commands.choices(
        sort=SEARCH_SORT_CHOICES,
        order=SEARCH_ORDER_CHOICES,
        display=CARD_DISPLAY_CHOICES,
    )
    @app_commands.autocomplete(query=autocomplete_cards)
    async def search(
        interaction: discord.Interaction,
        query: str,
        sort: str | None = None,
        order: str | None = None,
        variant: str = "",
        display: str = CardEmbedMode.SUMMARY.value,
    ) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.search(query, sort=sort, order=order)
        except BotError as error:
            await send_error(interaction, error)
            return
        if outcome.kind is CommandOutcomeKind.PICKER:
            await send_picker_followup(
                interaction,
                outcome.message,
                SearchResultsView(
                    owner_id=interaction.user.id,
                    source_query=query,
                    page=outcome.page,
                    total=outcome.total,
                    has_more=outcome.has_more,
                    choices=outcome.choices,
                    service=service,
                    sort=sort,
                    order=order,
                    variant_position=variant,
                    display_mode=display,
                ),
            )
            return
        await send_outcome(
            interaction,
            outcome,
            variant_position=variant,
            display_mode=display,
        )

    @bot.tree.command(name="random", description="Post a random Poneglyph card")
    @app_commands.describe(
        query="Optional Poneglyph query or simple random filters",
        variant="Variant index or name to show first; examples: 0, alt, sp, manga",
        display=(
            "Card embed detail level; summary is compact, detailed is current full view"
        ),
    )
    @app_commands.choices(display=CARD_DISPLAY_CHOICES)
    @app_commands.autocomplete(query=autocomplete_cards)
    async def random_card(
        interaction: discord.Interaction,
        query: str = "",
        variant: str = "",
        display: str = CardEmbedMode.SUMMARY.value,
    ) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=False)
        try:
            outcome = await service.random(query)
        except BotError as error:
            await send_error(interaction, error)
            return
        await send_outcome(
            interaction,
            outcome,
            variant_position=variant,
            display_mode=display,
        )

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
            await send_picker_followup(
                interaction,
                outcome.message,
                CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=card,
                    action="faq",
                    choices=outcome.choices,
                    service=service,
                ),
            )
            return
        await send_outcome(interaction, outcome, public_channel=True)

    @bot.tree.command(name="price", description="Post Poneglyph price history")
    @app_commands.describe(
        card="Card number or Poneglyph query",
        days="Days of price history",
    )
    @app_commands.autocomplete(card=autocomplete_cards)
    async def price(
        interaction: discord.Interaction,
        card: str,
        days: app_commands.Range[int, 1, 365] = 30,
    ) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.price(card, days=days)
        except BotError as error:
            await send_error(interaction, error)
            return
        if outcome.kind is CommandOutcomeKind.PICKER:
            await send_picker_followup(
                interaction,
                outcome.message,
                CardSelectView(
                    owner_id=interaction.user.id,
                    source_query=card,
                    action="price",
                    choices=outcome.choices,
                    service=service,
                    price_days=days,
                ),
            )
            return
        await send_outcome(interaction, outcome, public_channel=True)

    @bot.tree.command(name="help", description="Show bot help")
    async def help_command(interaction: discord.Interaction) -> None:
        service = _require_service(command_service)
        await interaction.response.send_message(service.help().message, ephemeral=True)

    _registered_commands = (card, search, random_card, faq, price, help_command)
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
                elif outcome.kind is CommandOutcomeKind.PICKER and outcome.choices:
                    first_choice = outcome.choices[0]
                    try:
                        selected_outcome = await service.card(first_choice.card_number)
                    except BotError as error:
                        await message.channel.send(error.user_message)
                        continue
                    if (
                        selected_outcome.kind is CommandOutcomeKind.PUBLIC_CARD
                        and selected_outcome.card
                    ):
                        await message.channel.send(
                            BRACKET_FIRST_MATCH_NOTE.format(query=query),
                            embed=build_card_embed(selected_outcome.card),
                        )
                    elif selected_outcome.message:
                        await message.channel.send(selected_outcome.message)
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
