import json
import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from client import TwitchMiner

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


class WebsocketClient:
    
    WS_URL = "wss://pubsub-edge.twitch.tv/v1"
    
    def __init__(self, miner: "TwitchMiner"):
        self.miner = miner
        self.ws: Optional[any] = None
        self.running = False
        self._ping_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None
        
    async def connect(self):
        if not WEBSOCKETS_AVAILABLE:
            return
        try:
            import websockets
            self.ws = await websockets.connect(self.WS_URL)
            self.running = True
            await self._subscribe()
            self._ping_task = asyncio.create_task(self._ping_loop())
            self._listen_task = asyncio.create_task(self._listen_loop())
        except:
            pass
            
    async def disconnect(self):
        self.running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()
            
    async def _subscribe(self):
        if not self.ws or not self.miner.user_id:
            return
        topics = [
            f"user-drop-events.{self.miner.user_id}",
            f"onsite-notifications.{self.miner.user_id}",
        ]
        message = {
            "type": "LISTEN",
            "data": {
                "topics": topics,
                "auth_token": self.miner.access_token,
            }
        }
        await self.ws.send(json.dumps(message))
        
    async def _ping_loop(self):
        while self.running and self.ws:
            try:
                await self.ws.send(json.dumps({"type": "PING"}))
                await asyncio.sleep(180)
            except:
                break
                
    async def _listen_loop(self):
        while self.running and self.ws:
            try:
                message = await self.ws.recv()
                await self._handle_message(json.loads(message))
            except:
                break
                
    async def _handle_message(self, message: dict):
        msg_type = message.get("type")
        if msg_type == "RECONNECT":
            await self.disconnect()
            await asyncio.sleep(1)
            await self.connect()
        elif msg_type == "MESSAGE":
            data = message.get("data", {})
            topic = data.get("topic", "")
            if "user-drop-events" in topic:
                await self._handle_drop_event(data)
                
    async def _handle_drop_event(self, data: dict):
        try:
            message_data = json.loads(data.get("message", "{}"))
            event_type = message_data.get("type")
            
            if event_type == "drop-progress":
                drop_id = message_data.get("drop_id")
                current_minutes = message_data.get("current_progress_min", 0)
                if drop_id in self.miner.active_drops:
                    drop = self.miner.active_drops[drop_id]
                    drop.current_minutes = current_minutes

            elif event_type == "drop-claim":
                drop_data = message_data.get("data", {})
                drop_id = drop_data.get("drop_id")
                drop_instance_id = drop_data.get("drop_instance_id")
                if drop_id and drop_instance_id and drop_id in self.miner.active_drops:
                    drop = self.miner.active_drops[drop_id]
                    drop.claim_id = drop_instance_id
                    # мобильные токены — API, веб — браузер
                    if self.miner.is_mobile:
                        await self.miner._claim_drop_api(drop)
                    else:
                        await self.miner.claim_drop(drop)
        except:
            pass
