from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, not_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

try:
    from database import AsyncSessionFactory
    from models.clan import Clan
    from models.interaction import ContactRequest, ExperienceEvent, Review
    from models.profile import Game, Profile
except ModuleNotFoundError:
    from src.database import AsyncSessionFactory
    from src.models.clan import Clan
    from src.models.interaction import ContactRequest, ExperienceEvent, Review
    from src.models.profile import Game, Profile


@dataclass(slots=True)
class PlatformRepository:
    """Queries that always identify owners by ``(platform, external id)``.

    Telegram's legacy repositories still accept a bare Telegram ID.  All new
    cross-platform code goes through this class so a Discord snowflake can
    never be mistaken for a Telegram chat ID.
    """

    session_factory: async_sessionmaker

    async def get_profile(self, platform: str, user_id: int) -> Profile | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Profile)
                .where(Profile.platform == platform, Profile.user_id == user_id)
                .options(selectinload(Profile.games))
            )
            return result.scalar_one_or_none()

    async def get_profile_by_id(self, profile_id: int) -> Profile | None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Profile)
                .where(Profile.id == profile_id)
                .options(selectinload(Profile.games))
            )
            return result.scalar_one_or_none()

    async def save_profile(
        self,
        *,
        platform: str,
        user_id: int,
        nickname: str,
        age: int | None,
        gender: str | None,
        games: dict[str, str | None],
        game_details: dict[str, dict[str, str | None]] | None = None,
        about: str,
        goals: list[str],
        convenient_time: list[str],
        contact_tag: str | None = None,
        photo: str | None = None,
        photo_origin: str | None = None,
        is_active: bool = True,
    ) -> Profile:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Profile)
                .where(Profile.platform == platform, Profile.user_id == user_id)
                .options(selectinload(Profile.games))
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                profile = Profile(
                    platform=platform,
                    user_id=user_id,
                    nickname=nickname,
                    age=age,
                    telegram_tag=contact_tag,
                    gender=gender,
                    about=about,
                    goals=goals,
                    convenient_time=convenient_time,
                    photo=photo,
                    photo_origin=photo_origin,
                    is_active=is_active,
                    self_deactivated=False,
                    teammate_ids=[],
                    experience=50,
                    send_first_message=False,
                    last_activity_day=date.today(),
                    days_series=1,
                )
                session.add(profile)
                await session.flush()
            else:
                profile.nickname = nickname
                profile.age = age
                profile.gender = gender
                profile.about = about
                profile.goals = goals
                profile.convenient_time = convenient_time
                if contact_tag is not None:
                    profile.telegram_tag = contact_tag
                profile.is_active = is_active
                if photo is not None:
                    profile.photo = photo
                    profile.photo_origin = photo_origin
                await session.execute(delete(Game).where(Game.profile_id == profile.id))

            for name, rank in games.items():
                details = (game_details or {}).get(name, {})
                session.add(
                    Game(
                        name=name,
                        rank=rank,
                        server=details.get("server"),
                        faction=details.get("faction"),
                        gallery=[],
                        profile_id=profile.id,
                    )
                )

            await session.commit()
            return await self.get_profile(platform, user_id)

    async def update_photo(
        self, platform: str, user_id: int, reference: str | None, origin: str | None
    ) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Profile)
                .where(Profile.platform == platform, Profile.user_id == user_id)
                .values(photo=reference, photo_origin=origin)
            )
            await session.commit()

    async def set_profile_active(
        self, platform: str, user_id: int, active: bool
    ) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(Profile)
                .where(Profile.platform == platform, Profile.user_id == user_id)
                .values(is_active=active, self_deactivated=not active)
            )
            await session.commit()

    async def delete_profile(self, platform: str, user_id: int) -> None:
        async with self.session_factory() as session:
            profile_id = await session.scalar(
                select(Profile.id).where(
                    Profile.platform == platform, Profile.user_id == user_id
                )
            )
            if profile_id is not None:
                await session.execute(delete(Game).where(Game.profile_id == profile_id))
                await session.execute(delete(Profile).where(Profile.id == profile_id))
                await session.commit()

    async def search_profiles(
        self,
        *,
        viewer_platform: str,
        viewer_user_id: int,
        game: str,
        rank: str | None = None,
        goal: str | None = None,
        server: str | None = None,
        faction: str | None = None,
        limit: int = 100,
    ) -> list[Profile]:
        own_account = and_(
            Profile.platform == viewer_platform,
            Profile.user_id == viewer_user_id,
        )
        query = (
            select(Profile)
            .join(Profile.games)
            .where(Profile.is_active.is_(True), Game.name == game, not_(own_account))
            .options(selectinload(Profile.games))
            .distinct()
            .limit(limit)
        )
        if rank:
            query = query.where(Game.rank == rank)
        if goal:
            query = query.where(Profile.goals.contains([goal]))
        if server:
            query = query.where(Game.server == server)
        if faction:
            query = query.where(Game.faction == faction)

        async with self.session_factory() as session:
            profiles = (await session.execute(query)).scalars().all()
            return sorted(
                profiles,
                key=lambda p: (
                    any(
                        value is not None for value in (p.polite, p.skill, p.team_game)
                    ),
                    p.experience or 0,
                    bool(p.photo),
                ),
                reverse=True,
            )

    async def create_contact_request(
        self,
        *,
        sender_profile_id: int,
        target_profile_id: int,
        kind: str,
        game: str | None,
        message: str | None,
    ) -> ContactRequest:
        request = ContactRequest(
            sender_profile_id=sender_profile_id,
            target_profile_id=target_profile_id,
            kind=kind,
            game=game,
            message=message,
            status="sent",
            reminder_due_at=(
                datetime.now(timezone.utc) + timedelta(hours=24)
                if kind == "invite"
                else None
            ),
        )
        async with self.session_factory() as session:
            session.add(request)
            await session.commit()
            await session.refresh(request)
            return request

    async def get_contact_request(self, request_id: int) -> ContactRequest | None:
        async with self.session_factory() as session:
            return await session.get(ContactRequest, request_id)

    async def active_rating_requests(self) -> list[ContactRequest]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(ContactRequest).where(
                    ContactRequest.kind == "invite",
                    ContactRequest.reminder_sent_at.is_not(None),
                    ContactRequest.status.in_(("sent", "in_process")),
                )
            )
            return result.scalars().all()

    async def due_contact_requests(self, limit: int = 100) -> list[ContactRequest]:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            result = await session.execute(
                select(ContactRequest)
                .where(
                    ContactRequest.reminder_due_at <= now,
                    ContactRequest.reminder_sent_at.is_(None),
                    ContactRequest.status == "sent",
                )
                .order_by(ContactRequest.reminder_due_at)
                .limit(limit)
            )
            return result.scalars().all()

    async def mark_reminder_sent(self, request_id: int) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(ContactRequest)
                .where(ContactRequest.id == request_id)
                .values(reminder_sent_at=datetime.now(timezone.utc))
            )
            await session.commit()

    async def mark_contact_failed(self, request_id: int) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(ContactRequest)
                .where(ContactRequest.id == request_id)
                .values(status="delivery_failed")
            )
            await session.commit()

    async def set_contact_status(self, request_id: int, status: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(ContactRequest)
                .where(ContactRequest.id == request_id)
                .values(status=status)
            )
            await session.commit()

    async def upsert_review(
        self,
        *,
        reviewer_profile_id: int,
        target_profile_id: int,
        contact_request_id: int | None,
        polite: int,
        skill: int,
        team_game: int,
    ) -> bool:
        scores = (polite, skill, team_game)
        if any(score < 1 or score > 5 for score in scores):
            raise ValueError("Scores must be between 1 and 5")

        async with self.session_factory() as session:
            is_new = not bool(
                await session.scalar(
                    select(Review.id).where(
                        Review.reviewer_profile_id == reviewer_profile_id,
                        Review.target_profile_id == target_profile_id,
                    )
                )
            )
            statement = pg_insert(Review).values(
                reviewer_profile_id=reviewer_profile_id,
                target_profile_id=target_profile_id,
                contact_request_id=contact_request_id,
                polite=polite,
                skill=skill,
                team_game=team_game,
            )
            statement = statement.on_conflict_do_update(
                constraint="uq_profile_review_pair",
                set_={
                    "contact_request_id": statement.excluded.contact_request_id,
                    "polite": statement.excluded.polite,
                    "skill": statement.excluded.skill,
                    "team_game": statement.excluded.team_game,
                    "updated_at": func.now(),
                },
            )
            await session.execute(statement)

            averages = (
                await session.execute(
                    select(
                        func.avg(Review.polite),
                        func.avg(Review.skill),
                        func.avg(Review.team_game),
                        func.count(Review.id),
                    ).where(Review.target_profile_id == target_profile_id)
                )
            ).one()
            target = await session.get(Profile, target_profile_id)
            legacy_count = target.legacy_review_count or 0
            new_count = int(averages[3] or 0)

            def blended(legacy: float | None, current: float | None) -> float | None:
                if current is None:
                    return legacy
                if legacy is None or legacy_count == 0:
                    return float(current)
                return (float(legacy) * legacy_count + float(current) * new_count) / (
                    legacy_count + new_count
                )

            await session.execute(
                update(Profile)
                .where(Profile.id == target_profile_id)
                .values(
                    polite=blended(target.legacy_polite, averages[0]),
                    skill=blended(target.legacy_skill, averages[1]),
                    team_game=blended(target.legacy_team_game, averages[2]),
                )
            )
            await session.commit()
            return is_new

    async def award_rating_experience(
        self, profile_id: int, target_profile_id: int
    ) -> tuple[bool, int, int]:
        """Award +10 XP for a new review, capped at three awards per UTC day."""
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with self.session_factory() as session:
            profile = await session.get(Profile, profile_id, with_for_update=True)
            if profile is None:
                raise LookupError("Profile not found")
            duplicate = await session.scalar(
                select(ExperienceEvent.id).where(
                    ExperienceEvent.profile_id == profile_id,
                    ExperienceEvent.event_type == "rating",
                    ExperienceEvent.reference_type == "profile",
                    ExperienceEvent.reference_id == target_profile_id,
                )
            )
            old_level = (profile.experience or 0) // 100 + 1
            if duplicate:
                return False, old_level, old_level
            today_count = await session.scalar(
                select(func.count(ExperienceEvent.id)).where(
                    ExperienceEvent.profile_id == profile_id,
                    ExperienceEvent.event_type == "rating",
                    ExperienceEvent.created_at >= day_start,
                )
            )
            if (today_count or 0) >= 3:
                return False, old_level, old_level
            session.add(
                ExperienceEvent(
                    profile_id=profile_id,
                    event_type="rating",
                    amount=10,
                    reference_type="profile",
                    reference_id=target_profile_id,
                )
            )
            profile.experience = (profile.experience or 0) + 10
            new_level = profile.experience // 100 + 1
            await session.commit()
            return True, old_level, new_level

    async def track_daily_activity(self, profile_id: int) -> tuple[int, int, int]:
        """Apply the daily +50 XP and every-fifth-consecutive-day +25 XP."""
        today = date.today()
        async with self.session_factory() as session:
            profile = await session.get(Profile, profile_id, with_for_update=True)
            if profile is None:
                raise LookupError("Profile not found")
            old_level = (profile.experience or 0) // 100 + 1
            diff = (today - profile.last_activity_day).days
            if diff <= 0:
                return old_level, old_level, 0
            profile.days_series = (profile.days_series or 0) + 1 if diff == 1 else 1
            amount = 50 + (25 if profile.days_series % 5 == 0 else 0)
            profile.experience = (profile.experience or 0) + amount
            profile.last_activity_day = today
            new_level = profile.experience // 100 + 1
            await session.commit()
            return old_level, new_level, amount

    async def accept_clan_application(
        self, request_id: int, leader_profile_id: int
    ) -> tuple[Profile | None, bool]:
        """Accept once and award the applicant +30 XP exactly once."""
        async with self.session_factory() as session:
            request = await session.get(
                ContactRequest, request_id, with_for_update=True
            )
            if (
                request is None
                or request.kind != "clan_application"
                or request.target_profile_id != leader_profile_id
            ):
                return None, False
            applicant = await session.get(
                Profile, request.sender_profile_id, with_for_update=True
            )
            if applicant is None:
                return None, False
            if request.status == "accepted":
                return applicant, False
            if request.status not in {"sent", "in_process"}:
                return None, False
            request.status = "accepted"
            session.add(
                ExperienceEvent(
                    profile_id=applicant.id,
                    event_type="clan_acceptance",
                    amount=30,
                    reference_type="contact_request",
                    reference_id=request.id,
                )
            )
            applicant.experience = (applicant.experience or 0) + 30
            await session.commit()
            return applicant, True

    async def add_experience(self, profile_id: int, amount: int) -> tuple[int, int]:
        async with self.session_factory() as session:
            profile = await session.get(Profile, profile_id)
            if profile is None:
                raise LookupError("Profile not found")
            old_level = (profile.experience or 0) // 100 + 1
            profile.experience = (profile.experience or 0) + amount
            new_level = profile.experience // 100 + 1
            await session.commit()
            return old_level, new_level

    async def award_first_message(
        self, profile_id: int, amount: int = 20
    ) -> tuple[bool, int, int]:
        """Atomically award the one-time first-message bonus."""
        async with self.session_factory() as session:
            profile = await session.get(Profile, profile_id, with_for_update=True)
            if profile is None:
                raise LookupError("Profile not found")
            old_level = (profile.experience or 0) // 100 + 1
            if profile.send_first_message:
                return False, old_level, old_level
            profile.send_first_message = True
            profile.experience = (profile.experience or 0) + amount
            new_level = profile.experience // 100 + 1
            await session.commit()
            return True, old_level, new_level

    async def create_clan(
        self,
        *,
        platform: str,
        user_id: int,
        name: str,
        game: str,
        description: str,
        demands: str,
        server: str | None = None,
        faction: str | None = None,
        photo: str | None = None,
        photo_origin: str | None = None,
    ) -> Clan:
        clan = Clan(
            platform=platform,
            user_id=user_id,
            name=name,
            game=game,
            description=description,
            demands=demands,
            server=server,
            faction=faction,
            add_info=None,
            photo=photo,
            photo_origin=photo_origin,
        )
        async with self.session_factory() as session:
            session.add(clan)
            await session.commit()
            await session.refresh(clan)
            return clan

    async def get_clan_by_id(self, clan_id: int) -> Clan | None:
        async with self.session_factory() as session:
            return await session.get(Clan, clan_id)

    async def update_clan(
        self,
        *,
        clan_id: int,
        platform: str,
        user_id: int,
        name: str,
        game: str,
        description: str,
        demands: str,
        server: str | None,
        faction: str | None,
    ) -> Clan | None:
        async with self.session_factory() as session:
            clan = await session.get(Clan, clan_id)
            if not clan or clan.platform != platform or clan.user_id != user_id:
                return None
            clan.name = name
            clan.game = game
            clan.description = description
            clan.demands = demands
            clan.server = server
            clan.faction = faction
            await session.commit()
            await session.refresh(clan)
            return clan

    async def update_clan_photo(
        self, clan_id: int, platform: str, user_id: int, photo: str, origin: str
    ) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                update(Clan)
                .where(
                    Clan.id == clan_id,
                    Clan.platform == platform,
                    Clan.user_id == user_id,
                )
                .values(photo=photo, photo_origin=origin)
            )
            await session.commit()
            return bool(result.rowcount)

    async def delete_clan(self, clan_id: int, platform: str, user_id: int) -> bool:
        async with self.session_factory() as session:
            result = await session.execute(
                delete(Clan).where(
                    Clan.id == clan_id,
                    Clan.platform == platform,
                    Clan.user_id == user_id,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def own_clans(self, platform: str, user_id: int) -> list[Clan]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Clan)
                .where(Clan.platform == platform, Clan.user_id == user_id)
                .order_by(Clan.created_at.desc())
            )
            return result.scalars().all()

    async def search_clans(
        self,
        platform: str,
        user_id: int,
        game: str,
        server: str | None = None,
        faction: str | None = None,
        limit: int = 100,
    ) -> list[Clan]:
        query = select(Clan).where(
            Clan.game == game,
            not_(and_(Clan.platform == platform, Clan.user_id == user_id)),
        )
        if server:
            query = query.where(Clan.server == server)
        if faction:
            query = query.where(Clan.faction == faction)
        query = query.order_by(Clan.created_at.desc()).limit(limit)
        async with self.session_factory() as session:
            result = await session.execute(query)
            return result.scalars().all()


platform_repository = PlatformRepository(AsyncSessionFactory)
