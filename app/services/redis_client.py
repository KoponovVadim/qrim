import redis
import json
from typing import Optional
from app.config import settings


class RedisClient:
    def __init__(self):
        self.client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
    
    def get_state(self, user_id: int) -> Optional[dict]:
        data = self.client.get(f"state:{user_id}")
        return json.loads(data) if data else None
    
    def set_state(self, user_id: int, state: dict):
        self.client.setex(
            f"state:{user_id}",
            settings.REDIS_TTL,
            json.dumps(state)
        )
    
    def delete_state(self, user_id: int):
        self.client.delete(f"state:{user_id}")
    
    def get_context(self, user_id: int) -> list:
        data = self.client.get(f"context:{user_id}")
        return json.loads(data) if data else []
    
    def add_to_context(self, user_id: int, message: dict):
        context = self.get_context(user_id)
        context.append(message)
        if len(context) > 10:
            context = context[-10:]
        self.client.setex(
            f"context:{user_id}",
            settings.REDIS_TTL,
            json.dumps(context)
        )


redis_client = RedisClient()
