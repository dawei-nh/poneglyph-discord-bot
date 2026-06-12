# Discord Developer Portal Setup

This bot needs a Discord application, a bot token, and a server install that grants
application commands plus the channel permissions required to post embeds.

## Create the application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications).
2. Select **New Application**.
3. Name the application and create it.
4. On **General Information**, copy the **Application ID**. Discord uses this as
   the OAuth2 `client_id` when you build an invite URL.

## Create the bot token

1. Open the application's **Bot** page.
2. Select **Add Bot** if the application does not already have one.
3. Select **Reset Token** or **Copy Token**.
4. Store the token as `DISCORD_TOKEN` or in the Docker secret file used by
   `DISCORD_TOKEN_FILE`.

Do not commit the token, paste it into issue comments, or bake it into a Docker
image. If the token is exposed, reset it in the portal and redeploy the bot with
the new value.

## Privileged Gateway Intents

Leave privileged intents off for the default slash-command deployment:

- **Presence Intent**: not needed.
- **Server Members Intent**: not needed.
- **Message Content Intent**: not needed unless bracket message lookup is enabled.

Only enable **Message Content Intent** when you also deploy with:

```text
OPTCG_ENABLE_BRACKET_MESSAGES=true
```

That optional mode lets the bot read new messages for `[[card-name]]` lookups.
Without that environment variable, the bot does not request message content even
if the portal toggle is on.

## Install scopes and permissions

Use the Developer Portal's **OAuth2** or **Installation** page to generate a
guild install link.

Required scopes:

```text
bot
applications.commands
```

Minimal bot permissions:

```text
View Channels
Send Messages
Embed Links
```

These permissions allow the bot to see the target channel, post public command
results, and render card embeds. Do not grant **Administrator** for this bot.

The matching permissions integer is `19456`, so the invite URL shape is:

```text
https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&permissions=19456&scope=bot%20applications.commands
```

Replace `<APPLICATION_ID>` with the value from the application's **General
Information** page.

## Invite the bot to a server

1. Open the generated OAuth2 URL in a browser.
2. Choose the target server. Your Discord account needs **Manage Server** on that
   server.
3. Review the scopes and permissions.
4. Authorize the install.
5. If the server uses channel-specific permission overwrites, confirm the bot's
   role still has **View Channels**, **Send Messages**, and **Embed Links** in
   every channel where public card posts should work.

If you change the permission set later, re-open the generated OAuth2 URL and
authorize the bot again. Existing installs do not automatically receive new OAuth2
permission grants.

## Start the bot

Deploy the container with the token configured. See
[Docker Deployment](docker.md) for Docker, Compose secrets, and runtime settings.

The bot syncs global slash commands during startup. New or changed commands can
take a few minutes to appear in Discord clients after startup.

## Smoke test in Discord

Run these checks in the server after the bot is online:

1. `/help` should answer ephemerally.
2. `/search query:luffy` should show private browse results.
3. Selecting a result from `/search` should post the selected card publicly.
4. `/card query:OP01-001` should post the card publicly in a channel where the
   bot can send messages and embeds.
5. If bracket lookup is enabled, send `[[Monkey D. Luffy]]` in a channel the bot
   can view.

## Troubleshooting

### Slash commands do not appear

- Confirm the invite included `applications.commands`.
- Restart the bot and wait a few minutes for global command sync to propagate.
- In the Discord client, reload the app if command autocomplete looks stale.

### Public card posts fail or stay private

`/card`, `/faq`, `/price`, and selected `/search` cards may post public embeds.
If Discord returns `403 Missing Access`, check the server role and channel
overrides for **View Channels**, **Send Messages**, and **Embed Links**.

The private `/search` browsing UI can still work when public channel sends fail
because it uses ephemeral interaction responses until a card is selected.

### Bot starts with an invalid token error

Reset the bot token in the Developer Portal, update `DISCORD_TOKEN` or the
`DISCORD_TOKEN_FILE` secret, then restart the container.

### Bracket lookups do not respond

- Confirm `OPTCG_ENABLE_BRACKET_MESSAGES=true` is set in the container.
- Confirm **Message Content Intent** is enabled on the application's **Bot** page.
- Confirm the bot can view the channel where the message was sent.
