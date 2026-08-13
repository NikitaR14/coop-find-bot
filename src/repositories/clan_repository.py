from dataclasses import dataclass
from models.clan import Clan
from database import async_sessionmaker, AsyncSessionFactory
from sqlalchemy import and_, not_, select, update, insert


@dataclass
class ClanRepository:
    session_factory: async_sessionmaker

    async def create_clan(
        self,
        user_id: int,
        name: str,
        game: str,
        add_info: str | None,
        description: str,
        demands: str,
        photo: str = None,
        server: str = None,
        faction: str = None,
    ) -> None:
        query = insert(Clan).values(
            user_id=user_id,
            platform="telegram",
            name=name,
            game=game,
            add_info=add_info,
            description=description,
            demands=demands,
            photo=photo,
            photo_origin="telegram" if photo else None,
            server=server,
            faction=faction,
        )
        async with self.session_factory() as session:
            await session.execute(query)
            await session.commit()

    async def get_clans(self, user_id: int) -> list[Clan]:
        async with self.session_factory() as session:
            clan = (
                (
                    await session.execute(
                        select(Clan).where(
                            Clan.user_id == user_id, Clan.platform == "telegram"
                        )
                    )
                )
                .scalars()
                .all()
            )
            return clan

    async def get_clan_by_id(self, clan_id: int) -> Clan | None:
        async with self.session_factory() as session:
            clan = (
                await session.execute(select(Clan).where(Clan.id == clan_id))
            ).scalar_one_or_none()
            return clan

    async def get_clans_by_game(
        self,
        game: str,
        user_id: int,
        server: str | None = None,
        faction: str | None = None,
    ) -> list[Clan]:
        query = select(Clan).where(
            Clan.game == game,
            not_(and_(Clan.platform == "telegram", Clan.user_id == user_id)),
        )
        if server:
            query = query.where(Clan.server == server)
        if faction:
            query = query.where(Clan.faction == faction)
        async with self.session_factory() as session:
            clans = (await session.execute(query)).scalars().all()
            return clans

    async def update_clan_photo(self, clan_id: int, new_photo: str) -> None:
        async with self.session_factory() as session:
            if clan := await self.get_clan_by_id(clan_id=clan_id):
                await session.execute(
                    update(Clan)
                    .where(Clan.id == clan_id)
                    .values(
                        photo=new_photo,
                        photo_origin="telegram" if new_photo else None,
                    )
                )
                await session.commit()

    async def delete_clan(self, clan_id: int) -> None:
        async with self.session_factory() as session:
            if clan := await self.get_clan_by_id(clan_id=clan_id):
                await session.delete(clan)
                await session.commit()

    async def update_name(self, clan_id: int, name: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Clan).where(Clan.id == clan_id).values(name=name)
            )
            await session.commit()

    async def update_game(self, clan_id: int, game: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Clan).where(Clan.id == clan_id).values(game=game)
            )
            await session.commit()

    async def update_description(self, clan_id: int, desc: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Clan).where(Clan.id == clan_id).values(description=desc)
            )
            await session.commit()

    async def update_demands(self, clan_id: int, demands: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Clan).where(Clan.id == clan_id).values(demands=demands)
            )
            await session.commit()

    async def update_add_info(self, clan_id: int, add_info: str | None) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Clan).where(Clan.id == clan_id).values(add_info=add_info)
            )
            await session.commit()

    async def update_mmo_info(
        self, clan_id: int, *, server: str, faction: str, game: str | None = None
    ) -> None:
        values = {"server": server, "faction": faction}
        if game is not None:
            values["game"] = game
        async with self.session_factory() as session:
            await session.execute(
                update(Clan).where(Clan.id == clan_id).values(**values)
            )
            await session.commit()


clan_repository = ClanRepository(session_factory=AsyncSessionFactory)
