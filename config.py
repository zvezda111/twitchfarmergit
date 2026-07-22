from pathlib import Path
from typing import Optional
from loguru import logger
import json

class MinerConfig:
    
    def __init__(self,
        tokens: list[str] | None = None,
        data_dir: Path | None = None,
    ):
        if data_dir is None:
            data_dir = Path("data")
        self.data_dir = data_dir
        self.tokens_file = data_dir / "accounts.json"
        self.streamers_file = data_dir / "streamers.txt"
        self.log_level = "INFO"
        self.connection_timeout = 30
        self.retry_delay = 5
        self.max_retries = 3
        self.watch_interval = 60
        self.inventory_refresh = 300
        self.inventory_check_minutes = 1
        self.offline_check_interval = 120
        self.proxy: Optional[str] = None
        self.streamers: list[str] = []
        self.all_tokens: list[str] = tokens
        self.auth_token = self.all_tokens[0] if self.all_tokens else ""
        self._load_streamers()

    def _load_all_tokens(self) -> list[str]:
        try:
            data = self.tokens_file
            tokens = [a['token'] for a in data.get('accounts', []) if a.get('token')]
            if tokens:
                logger.info(f"Токенов: {len(tokens)}")
            return tokens
        except:
            return []

    def _load_streamers(self):
        try:
            with open(self.streamers_file, 'r', encoding='utf-8') as f:
                streamers = []
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    streamer = line.lower().strip()
                    if streamer.startswith('@'):
                        streamer = streamer[1:]
                    if 'twitch.tv/' in streamer:
                        streamer = streamer.split('twitch.tv/')[-1]
                    if '?' in streamer:
                        streamer = streamer.split('?')[0]
                    if streamer:
                        streamers.append(streamer)
                self.streamers = streamers
                if streamers:
                    logger.info(f"Стримеров: {len(streamers)}")
        except:
            pass

