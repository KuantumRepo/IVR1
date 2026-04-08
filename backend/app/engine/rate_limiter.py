import asyncio
import time

class RateLimiter:
    """Safe asyncio exact token bucket rate limiter to strictly enforce calls-per-second limiting"""
    def __init__(self, calls_per_second: float):
        self.cps = calls_per_second
        self.tokens = self.cps
        self.last_update = time.monotonic()
        
    async def wait(self):
        while True:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens += elapsed * self.cps
            
            if self.tokens > self.cps:
                self.tokens = self.cps
                
            self.last_update = now
            
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
                
            sleep_time = (1.0 - self.tokens) / self.cps
            await asyncio.sleep(sleep_time)
