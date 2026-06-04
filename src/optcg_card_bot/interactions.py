from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.abc import Messageable
from discord.ext import commands

from optcg_card_bot.commands import CommandOutcome, CommandOutcomeKind, CommandService
from optcg_card_bot.embeds import build_card_embed, build_faq_embed
from optcg_card_bot.errors import BotError
from optcg_card_bot.search import CardChoice


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
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)
        return
    if outcome.kind is CommandOutcomeKind.PUBLIC_FAQ and outcome.card is not None:
        embed = build_faq_embed(outcome.card, outcome.faq_entries)
        if public_channel and hasattr(interaction.channel, "send"):
            channel = cast("Messageable", interaction.channel)
            await channel.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed, ephemeral=False)
        return
    if outcome.kind is CommandOutcomeKind.EPHEMERAL_MESSAGE:
        await interaction.followup.send(outcome.message, ephemeral=True)
        return
    await interaction.followup.send("No response was produced.", ephemeral=True)


async def send_error(interaction: discord.Interaction, error: BotError) -> None:
    await interaction.followup.send(error.user_message, ephemeral=True)


class SyncingBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.tree.sync()


def create_bot(command_service: CommandService | None) -> commands.Bot:
    intents = discord.Intents.default()
    bot = SyncingBot(command_prefix=commands.when_mentioned, intents=intents)

    @bot.tree.command(name="card", description="Search and post a Poneglyph card")
    @app_commands.describe(query="Poneglyph query or card number")
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
    @app_commands.describe(query="Poneglyph query")
    async def search(interaction: discord.Interaction, query: str) -> None:
        service = _require_service(command_service)
        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await service.search(query)
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
        await send_outcome(interaction, outcome)

    @bot.tree.command(name="random", description="Post a random Poneglyph card")
    @app_commands.describe(query="Optional Poneglyph query or simple random filters")
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
