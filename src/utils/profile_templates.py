from models.profile import Profile
from utils.constants import FULL_PROFILE_SAMPLE, PROFILE_ADD_INFO, RAVEN_PROFILE_ADD_INFO
from html import escape



async def get_main_template(profile: Profile, user_rank: str = "") -> str:
    return FULL_PROFILE_SAMPLE.format(
            nickname=escape(profile.nickname),
            age=escape(str(profile.age or "Не указан")),
            telegram_tag= escape("@" + profile.telegram_tag if profile.telegram_tag else "Нет"),
            platform="🔵 Discord" if profile.platform == "discord" else "✈️ Telegram",
            gender=escape(profile.gender if profile.gender else "Нет"),
            level=escape(str(profile.experience // 100 + 1)),
            polite=escape(str(round(profile.polite, 1)) + "⭐" if profile.polite is not None else "Нет оценок"),
            skill=escape(str(round(profile.skill, 1)) + "⭐" if profile.skill is not None else "Нет оценок"),
            team_game=escape(str(round(profile.team_game, 1)) + "⭐" if profile.team_game is not None else "Нет оценок"),
            games=escape(profile.games_str),
            rank=user_rank,
            add_info=PROFILE_ADD_INFO.format(time=", ".join(profile.convenient_time) if profile.convenient_time else "Не указано", 
                                             about=escape(profile.about), goal=", ".join(profile.goals) if profile.goals else "Не указаны")
        )

async def get_warcraft_profile_template(profile: Profile) -> str:
    games = {game.name: game.rank for game in profile.games}

    if games.get("Warcraft", False):
        user_rank = f"\n<b>Ранг:</b>\n"
        subranks = []
        for subrank in games["Warcraft"].split(";")[:-1]:
            mode, info = subrank.split("/")
            subranks.append(f"- {mode}: {info}")
        user_rank += "\n".join(subranks)
    else:
        user_rank = f"\n<b>Ранг:</b> Не указан"

    return await get_main_template(profile, user_rank)


async def get_other_game_profile_template(profile: Profile, game: str) -> str:
    games = {item.name: item for item in profile.games}

    if games.get(game) and games[game].rank:
        user_rank = f"\n<b>Ранг:</b> {escape(games[game].rank)}"
    else:
        user_rank = f"\n<b>Ранг:</b> Не указан"
    if games.get(game) and games[game].server:
        user_rank += f"\n<b>Сервер:</b> {escape(games[game].server)}"
    if games.get(game) and games[game].faction:
        user_rank += f"\n<b>Фракция:</b> {escape(games[game].faction)}"

    return await get_main_template(profile, user_rank)

async def get_raven_main_template(profile: Profile, user_rank: str = "", add_info: str = "") -> str:
    return FULL_PROFILE_SAMPLE.format(
            nickname=escape(profile.nickname),
            age=escape(str(profile.age or "Не указан")),
            telegram_tag= escape("@" + profile.telegram_tag if profile.telegram_tag else "Нет"),
            platform="🔵 Discord" if profile.platform == "discord" else "✈️ Telegram",
            gender=escape(profile.gender if profile.gender else "Нет"),
            level=escape(str(profile.experience // 100 + 1)),
            polite=escape(str(round(profile.polite, 1)) + "⭐" if profile.polite is not None else "Нет оценок"),
            skill=escape(str(round(profile.skill, 1)) + "⭐" if profile.skill is not None else "Нет оценок"),
            team_game=escape(str(round(profile.team_game, 1)) + "⭐" if profile.team_game is not None else "Нет оценок"),
            games=escape(profile.games_str),
            rank=user_rank,
            add_info=add_info
        )

async def get_raven2_profile_template(profile: Profile, game: str) -> str:
    games = {game.name: game.rank for game in profile.games}

    if games.get(game, False):
        parts = games[game].split("@")

        if game == "Raven 2":
            server = f"{parts[0]} - {parts[1]}"
        else:
            server = parts[0]

        if game == "Lineage 2M":
            class_ = f"{parts[1]}-{parts[2]}"
        else:
            class_ = parts[2]

        level = parts[3]

        if parts[-3] == "Да":
            donate = f"{parts[-3]}, {parts[-2]}"
        else:
            donate = "Нет"


        add_info = RAVEN_PROFILE_ADD_INFO.format(
                                             server=escape(server),
                                             class_=escape(class_),
                                             level=escape(level),
                                             time=escape(", ".join(profile.convenient_time) if profile.convenient_time else "Не указано"), 
                                             donate=escape(donate),
                                             about=escape(profile.about), 
                                             goal=escape(", ".join(profile.goals) if profile.goals else "Не указаны"))
        
        return await get_raven_main_template(profile, "", add_info)
    

async def get_profile_template(profile: Profile, game: str) -> str:
    if game == "Warcraft":
        profile_template = await get_warcraft_profile_template(profile)
    elif game in ("Raven 2", "Lineage 2M"):
        profile_template = await get_raven2_profile_template(profile, game)
    else:
        profile_template = await get_other_game_profile_template(profile, game)

    return profile_template

async def get_profile_template_no_rank(profile: Profile) -> str:
    return await get_main_template(profile)

async def get_raven2_rank_template(game: str, rank: str) -> str:
    parts = rank.split("@")

    if game == "Raven 2":
        server = f"{parts[0]} - {parts[1]}"
    else:
        server = parts[0]

    if game == "Lineage 2M":
        class_ = f"{parts[1]}-{parts[2]}"
    else:
        class_ = parts[2]

    level = parts[3]
    stats = parts[4] if parts[4] != "-" else "Не указаны"

    if parts[-3] == "Да":
        donate = f"{parts[-3]}, {parts[-2] if parts[-2] != '-' else 'Не указан'}"
    else:
        donate = "Нет"
        
    transfer = parts[-1] if parts[-1] != "-" else "Не указан"

    return f"<b>Сервер</b>: {escape(server)}\n<b>Класс</b>: {escape(class_)}\n<b>Уровень</b>: {escape(level)}\n<b>Статы</b>: {escape(stats)}\n<b>Донат</b>: {escape(donate)}\n<b>Готов к трансферу</b>: {escape(transfer)}\n"

async def get_warcraft_rank_template(rank: str) -> str:
    parts = rank.split(";")[:-1]
    subranks = []
    for subrank in parts:
        mode, info = subrank.split("/")
        subranks.append(f"- {mode}: {info}")
    return "\n" + "\n".join(subranks)
