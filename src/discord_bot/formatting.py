import discord

try:
    from models.clan import Clan
    from models.profile import Profile
except ModuleNotFoundError:
    from src.models.clan import Clan
    from src.models.profile import Profile


def platform_badge(platform: str) -> str:
    return "🔵 Discord" if platform == "discord" else "✈️ Telegram"


def score(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} ⭐"


def profile_embed(profile: Profile, selected_game: str | None = None) -> discord.Embed:
    game_lines = []
    for game in profile.games:
        rank = f" — {game.rank}" if game.rank else ""
        details = ""
        if game.server:
            details += f"\n  Сервер: {game.server}"
        if game.faction:
            details += f"; фракция: {game.faction}"
        game_lines.append(f"• {game.name}{rank}{details}")
    embed = discord.Embed(
        title=profile.nickname,
        description=profile.about or "О себе не указано",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Возраст", value=str(profile.age or "Не указан"), inline=True)
    embed.add_field(name="Пол", value=profile.gender or "Не указан", inline=True)
    embed.add_field(
        name="Контакт",
        value=f"{platform_badge(profile.platform)} · {profile.telegram_tag or 'Не указан'}",
        inline=False,
    )
    embed.add_field(
        name="Игры и ранги", value="\n".join(game_lines) or "—", inline=False
    )
    embed.add_field(
        name="Цели", value=", ".join(profile.goals or []) or "—", inline=False
    )
    embed.add_field(
        name="Удобное время",
        value=", ".join(profile.convenient_time or []) or "—",
        inline=False,
    )
    embed.add_field(
        name="Репутация в TeamSeek",
        value=f"Уровень {(profile.experience or 0) // 100 + 1} ⚡",
        inline=False,
    )
    embed.add_field(name="Вежливость", value=score(profile.polite), inline=True)
    embed.add_field(name="Скилл", value=score(profile.skill), inline=True)
    embed.add_field(name="Командная игра", value=score(profile.team_game), inline=True)
    if selected_game:
        embed.set_footer(text=f"Поиск по игре: {selected_game}")
    return embed


def clan_embed(clan: Clan) -> discord.Embed:
    embed = discord.Embed(
        title=clan.name,
        description=clan.description,
        color=discord.Color.dark_teal(),
    )
    embed.add_field(name="Игра", value=clan.game, inline=True)
    embed.add_field(name="Платформа", value=platform_badge(clan.platform), inline=True)
    if clan.server:
        embed.add_field(name="Сервер", value=clan.server, inline=True)
    if clan.faction:
        embed.add_field(name="Фракция", value=clan.faction, inline=True)
    embed.add_field(name="Требования", value=clan.demands, inline=False)
    return embed
