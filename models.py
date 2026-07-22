import re
from typing import Optional
from datetime import datetime, timezone


def parse_timestamp(ts_string: str) -> datetime:
    try:
        return datetime.strptime(ts_string, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(ts_string, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class Game:
    
    def __init__(self, game_id: int, name: str):
        self.id = game_id
        self.name = name
        self._slug: Optional[str] = None
        
    @classmethod
    def from_data(cls, data: dict) -> "Game":
        return cls(
            game_id=int(data["id"]),
            name=data.get("displayName") or data["name"]
        )
        
    @property
    def slug(self) -> str:
        if self._slug:
            return self._slug
        slug = self.name.lower()
        slug = re.sub(r"'", '', slug)
        slug = re.sub(r'\W+', '-', slug)
        slug = re.sub(r'-{2,}', '-', slug.strip('-'))
        self._slug = slug
        return slug
        
    def __str__(self) -> str:
        return self.name
        
    def __repr__(self) -> str:
        return f"Game({self.id}, {self.name})"


class Drop:
    
    def __init__(self, drop_id: str, name: str, required_minutes: int, current_minutes: int = 0):
        self.id = drop_id
        self.name = name
        self.required_minutes = required_minutes
        self.current_minutes = current_minutes
        self.is_claimed = False
        self.claim_id: Optional[str] = None
        
    @classmethod
    def from_data(cls, data: dict) -> "Drop":
        drop = cls(
            drop_id=data["id"],
            name=data["name"],
            required_minutes=data["requiredMinutesWatched"],
        )
        if "self" in data and data["self"]:
            self_data = data["self"]
            drop.current_minutes = self_data.get("currentMinutesWatched", 0)
            drop.is_claimed = self_data.get("isClaimed", False)
            drop.claim_id = self_data.get("dropInstanceID")
        return drop
        
    @property
    def progress(self) -> int:
        if self.required_minutes == 0:
            return 100
        return min(100, int(self.current_minutes / self.required_minutes * 100))
        
    @property
    def can_earn(self) -> bool:
        return not self.is_claimed and self.current_minutes < self.required_minutes

    @property
    def can_claim(self) -> bool:
        if self.is_claimed:
            return False
        has_progress = self.current_minutes >= self.required_minutes
        has_claim_id = self.claim_id is not None
        return has_progress and has_claim_id

    def __repr__(self) -> str:
        return f"Drop({self.name}, {self.progress}%)"


class Campaign:

    def __init__(self, campaign_id: str, name: str, game: Game, starts_at: datetime, ends_at: datetime):
        self.id = campaign_id
        self.name = name
        self.game = game
        self.starts_at = starts_at
        self.ends_at = ends_at
        self.drops: list[Drop] = []

    @classmethod
    def from_data(cls, data: dict) -> "Campaign":
        game_data = data.get("game")
        if not game_data:
            raise ValueError("Campaign has no game")

        campaign = cls(
            campaign_id=data["id"],
            name=data["name"],
            game=Game.from_data(game_data),
            starts_at=parse_timestamp(data["startAt"]),
            ends_at=parse_timestamp(data["endAt"]),
        )

        drops_data = data.get("timeBasedDrops", []) or []
        for drop_data in drops_data:
            try:
                drop = Drop.from_data(drop_data)
                campaign.drops.append(drop)
            except:
                continue

        return campaign

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.starts_at <= now < self.ends_at

    @property
    def is_upcoming(self) -> bool:
        return self.starts_at > datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return f"Campaign({self.name}, {len(self.drops)} drops)"


class Channel:

    def __init__(self, channel_id: int, login: str, display_name: str, viewers: int = 0):
        self.id = channel_id
        self.login = login
        self.name = display_name
        self.viewers = viewers
        self.game: Optional[Game] = None

    @classmethod
    def from_stream(cls, data: dict) -> "Channel":
        broadcaster = data.get("broadcaster")
        if not broadcaster:
            raise ValueError("No broadcaster data")

        channel = cls(
            channel_id=int(broadcaster["id"]),
            login=broadcaster["login"],
            display_name=broadcaster["displayName"],
            viewers=data.get("viewersCount", 0),
        )

        game_data = data.get("game")
        if game_data:
            channel.game = Game.from_data(game_data)

        return channel

    def __repr__(self) -> str:
        return f"Channel({self.login}, {self.viewers} viewers)"
