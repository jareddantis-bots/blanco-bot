blanco-bot
===

[![Docker Image CI](https://github.com/jareddantis/blanco-bot/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/jareddantis/blanco-bot/actions/workflows/build-and-push.yml)
![Docker Pulls](https://img.shields.io/docker/pulls/jareddantis/blanco-bot)

This is a self-contained Discord music bot that supports pulling music metadata from Spotify, made with [Nextcord v2](https://nextcord.dev).

Music playback is handled by the [Mafic](https://github.com/ooliver1/mafic) client for the [Lavalink](https://github.com/lavalink-devs/Lavalink) server.

The bot stores settings in a local SQLite database. This database is populated automatically on first run, and the settings it will contain include the set volume level and queue repeat preferences per guild.

- [blanco-bot](#blanco-bot)
  - [Before you proceed](#before-you-proceed)
- [Requirements](#requirements)
- [Deployment](#deployment)
  - [Lavalink in composition](#lavalink-in-composition)
    - [IPv6 support](#ipv6-support)
  - [Debugging](#debugging)

## Before you proceed

**Do not monetize, or attempt to submit for verification, any instance of this bot.** The Lavalink audio server pulls audio data from YouTube, which goes against the [YouTube Terms of Service.](https://www.youtube.com/t/terms) At best, Discord will reject your application for verification, and at worst, your developer account will get banned.

You will need a working Lavalink server for your own bot instance to work; there is a list of free servers [here.](https://lavalink.darrennathanael.com/) You could also choose to run Lavalink along with your bot in a separate container. Follow everything in [Deployment](#deployment), then edit `docker-compose.yml` according to the instructions in [Lavalink in composition](#lavalink-in-composition).

# Requirements

This bot is self-contained, in that you do not have to install anything aside from Docker. All of the dependencies are included in the Docker image, which has been tested on Linux hosts using Docker CE, and on Windows and macOS hosts using Docker Desktop.

The bot image is built with both `linux/amd64` and `linux/arm64` support, so you can, for instance, run the bot on Apple Silicon with reasonable performance.

# Deployment

Make sure you have Docker installed and up-to-date. Also make sure that you have a bot token from [Discord,](https://discord.com/developers/applications) and that you have a client ID & secret pair from [Spotify.](https://developer.spotify.com/dashboard)

Create an empty directory and create a file named `config.yml` in it, with the following contents:

```yaml
bot:
  database: blanco.db
  discord_token: <your Discord bot token>
  inactivity_timeout: 120
spotify:
  client_id: <your client id>
  client_secret: <your client secret>
lavalink:
  - id: main
    server: localhost
    port: 2333
    password: youshallnotpass
    regions: 
      - us-central
      - us-east

    # Set to true if node supports SSL (https://, wss://)
    ssl: false                   
# You may add more than one node here
# - id: backup
#   ...
```

Edit the values with your Discord and Spotify tokens, along with the details of your chosen Lavalink server(s).

We also need to create an empty database file in the same folder, which will be used by the bot to store settings. Open a terminal, change your working directory to the repository root and run the following command:

```bash
touch blanco.db
```

Then create a `docker-compose.yml` file in the same folder with the following contents:

```yaml
version: '3.8'
services:
  blanco-bot:
    image: jareddantis/blanco-bot:latest
    container_name: blanco-bot
    volumes:
      - /YOUR/PATH/HERE/config.yml:/opt/app/config.yml
      - /YOUR/PATH/HERE/blanco.db:/opt/app/blanco.db
    restart: unless-stopped
```

Edit `/YOUR/PATH/HERE/config.yml` and `/YOUR/PATH/HERE/blanco.db` to match the paths to your `config.yml` and `blanco.db`.

Finally, in a terminal, run

```bash
docker compose up -d
```

This will cause the bot to run in the background after the container is built. Omit the `-d` if you want it to run in the foreground, printing logs to the terminal as they come. If you get an error regarding the `compose` command or the `docker-compose.yml` file, you might be running an old version of Docker - please update before trying again.

In case there is an update to the bot, just stop the container using

```
docker compose stop
```

then pull the latest bot image using

```
docker compose rm -f
docker compose pull blanco-bot
```

and start the container again using

```bash
docker compose up -d
```

## Lavalink in composition

If you want to host Lavalink alongside your bot, make sure you have enough resources to run both Lavalink and the bot. The absolute minimum is 1GB of RAM, which will be enough for a few guilds, but you will need more as your bot grows.

Download the Lavalink configuration file from [here.](https://github.com/freyacodes/Lavalink/blob/master/LavalinkServer/application.yml.example) Save it as `lavalink.yml`, next to your `docker-compose.yml` file.

Now edit `docker-compose.yml` such that it resembles the following, changing the paths as necessary:

```yaml
version: '3.8'
services:
  lavalink:
    image: ghcr.io/lavalink-devs/lavalink:v4
    container_name: lavalink
    environment:
      - _JAVA_OPTIONS=-Xmx1G # Set higher for larger bots
    volumes:
      - ./lavalink.yml:/opt/Lavalink/application.yml
    restart: unless-stopped
  bot:
    image: jareddantis/blanco-bot:latest
    container_name: blanco-bot
    volumes:
      - /YOUR/PATH/HERE/config.yml:/opt/app/config.yml
      - /YOUR/PATH/HERE/blanco.db:/opt/app/blanco.db
    restart: unless-stopped
```

Then edit the Lavalink configuration in `config.yml` to match the following:

```yaml
lavalink:
  - id: main
    port: 2333
    ssl: false
    regions: 
      - us-central
      - us-east

    # Must match the service name in docker-compose.yml
    server: lavalink

    # Must match the server password in lavalink.yml
    password: youshallnotpass
```

Then run `docker compose up -d` as usual.

### IPv6 support

If you want to run the Lavalink container with support for IPv6 (i.e., for use with [Tunnelbroker](https://blog.arbjerg.dev/2020/3/tunnelbroker-with-lavalink)), make sure **both** the Lavalink container and the bot container are running in host networking mode. You can do this by adding the following to `docker-compose.yml`:

```yaml
# ...
services:
  lavalink:
    # ...
    network_mode: host
  bot:
    # ...
    network_mode: host
```

You will also need to change the `server` value in `config.yml` to `localhost`:

```yaml
lavalink:
  - id: main
    server: localhost
    # ...
```

Configure your Lavalink server to bind to your desired IPv6 address blocks by editing `lavalink.yml` accordingly, then run `docker compose up -d`.

Note that this configuration is specific to Linux hosts - Docker does not support host networking on either Windows or macOS.

## Debugging

Blanco has the ability to switch to a debug mode, which at the moment is only used to register slash commands in a specified guild instead of globally like normal.

If you would like to enable debugging mode in your own instance, edit the `bot` section in `config.yml` as such, then (re)start your instance:

```yaml
bot:
  # ...
  debug:
    enabled: true
    guild_ids:
      - <your guild id>
      # can add more than 1 guild here
```
