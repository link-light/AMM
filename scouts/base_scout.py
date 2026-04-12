"""
Base Scout Interface

All scouts must inherit from BaseScout and implement:
- scan(): Scan data source and return raw data
- parse(): Parse raw data into standardized Signal format
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import List

from core.config import settings
from core.models import Signal
from core.queue import QueueManager
from gateway.gateway import AIGateway

logger = logging.getLogger(__name__)


class BaseScout(ABC):
    """
    Abstract base class for all scouts
    
    Scouts are responsible for discovering business opportunities
    from various sources (freelance platforms, GitHub, etc.)
    """
    
    def __init__(
        self,
        gateway: AIGateway = None,
        queue: QueueManager = None,
        config: dict = None
    ):
        self.gateway = gateway or AIGateway()
        self.queue = queue or QueueManager()
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def scan(self) -> List[dict]:
        """
        Scan the data source and return raw data
        
        Returns:
            List of raw data items (dicts)
        """
        pass
    
    @abstractmethod
    async def parse(self, raw_data: List[dict]) -> List[Signal]:
        """
        Parse raw data into standardized Signal format
        
        Args:
            raw_data: Raw data from scan()
            
        Returns:
            List of Signal objects
        """
        pass
    
    def _generate_id(self, item: dict) -> str:
        """Generate unique ID for deduplication"""
        # Use URL or content hash
        content = json.dumps(item, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def deduplicate(self, items: List[dict]) -> List[dict]:
        """
        Remove duplicate items based on URL + content hash
        
        Args:
            items: List of raw items
            
        Returns:
            List of unique items
        """
        seen = set()
        unique = []
        
        for item in items:
            # Generate fingerprint from URL + key fields
            url = item.get("url", "")
            title = item.get("title", "")
            fingerprint = hashlib.md5(
                f"{url}:{title}".encode()
            ).hexdigest()
            
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique.append(item)
        
        self.logger.debug(f"Deduplication: {len(items)} → {len(unique)}")
        return unique
    
    async def run_once(self):
        """
        Execute one scan cycle: scan → deduplicate → parse → enqueue
        
        This is the main entry point for running the scout.
        """
        self.logger.info(f"Starting scan: {self.__class__.__name__}")
        
        try:
            # Step 1: Scan
            raw = await self.scan()
            if not raw:
                self.logger.info("No data found in scan")
                return
            
            self.logger.info(f"Scanned {len(raw)} items")
            
            # Step 2: Deduplicate
            new_items = self.deduplicate(raw)
            
            # Step 3: Parse
            signals = await self.parse(new_items)
            
            # Step 4: Enqueue
            await self.queue.connect()
            for signal in signals:
                await self.queue.enqueue_signal_raw(signal.to_dict())
            
            self.logger.info(f"Discovered {len(signals)} new signals")
            
        except Exception as e:
            self.logger.error(f"Scan failed: {e}")
            raise
    
    async def run_continuous(self, interval_seconds: int = None):
        """
        Run scout continuously with sleep interval
        
        Args:
            interval_seconds: Seconds between scans (uses config if not specified)
        """
        import asyncio
        
        if interval_seconds is None:
            interval_seconds = self.config.get("interval", 1800)  # Default 30 min
        
        self.logger.info(
            f"Starting continuous scan (interval={interval_seconds}s)"
        )
        
        while True:
            try:
                await self.run_once()
            except Exception as e:
                self.logger.error(f"Scan error: {e}")
            
            self.logger.debug(f"Sleeping for {interval_seconds}s")
            await asyncio.sleep(interval_seconds)
