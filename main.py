"""
AI Money Machine - Main Entry Point

Usage:
    python main.py full      # Start all components
    python main.py api       # Start API only
    python main.py worker    # Start workers only
    python main.py scout     # Start scouts only
    python main.py orchestrator  # Start orchestrator only

Startup order:
1. Load configuration
2. Initialize database connection
3. Initialize Redis connection
4. Initialize AI Gateway
5. Start Celery Workers
6. Start Scouts (scheduled tasks)
7. Start Orchestrator (evaluator, dispatcher, reviewer)
8. Start FastAPI service
"""

import argparse
import asyncio
import logging
import signal
import sys
from typing import List

from core.config import settings
from core.database import close_db, init_db
from core.queue import queue_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.app.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ComponentRunner:
    """Manages running system components"""
    
    def __init__(self):
        self.tasks: List[asyncio.Task] = []
        self.running = False
    
    async def initialize(self):
        """Initialize core infrastructure"""
        logger.info("Initializing infrastructure...")
        
        # Database
        try:
            await init_db()
            logger.info("Database initialized")
        except Exception as e:
            logger.warning(f"Database init issue (may already exist): {e}")
        
        # Redis
        await queue_manager.connect()
        logger.info("Redis connected")
        
        # Gateway (singleton auto-initializes)
        from gateway.gateway import AIGateway
        AIGateway()
        logger.info("AI Gateway initialized")
    
    async def start_evaluator(self):
        """Start opportunity evaluator"""
        from orchestrator.evaluator import evaluator
        logger.info("Starting Evaluator...")
        await evaluator.run()
    
    async def start_dispatcher(self):
        """Start task dispatcher"""
        from orchestrator.dispatcher import dispatcher
        logger.info("Starting Dispatcher...")
        await dispatcher.run()
    
    async def start_reviewer(self):
        """Start quality reviewer"""
        from orchestrator.reviewer import reviewer
        logger.info("Starting Reviewer...")
        await reviewer.run()
    
    async def start_scout(self):
        """Start freelance scout (continuous)"""
        from scouts.freelance_scout import FreelanceScout
        scout = FreelanceScout()
        logger.info("Starting Freelance Scout...")
        await scout.run_continuous()
    
    async def start_worker(self, worker_type: str = "coding"):
        """Start a worker"""
        if worker_type == "coding":
            from workers.coding_worker import CodingWorker
            worker = CodingWorker()
            logger.info("Starting Coding Worker...")
            await worker.run()
    
    async def start_api(self):
        """Start FastAPI server"""
        import uvicorn
        logger.info("Starting API server on http://0.0.0.0:8000")
        config = uvicorn.Config(
            "api.main:app",
            host="0.0.0.0",
            port=8000,
            reload=settings.app.debug,
            log_level=settings.app.log_level.lower(),
        )
        server = uvicorn.Server(config)
        await server.serve()
    
    async def run_components(self, components: List[str]):
        """Run specified components concurrently"""
        await self.initialize()
        
        component_map = {
            "evaluator": self.start_evaluator,
            "dispatcher": self.start_dispatcher,
            "reviewer": self.start_reviewer,
            "scout": self.start_scout,
            "worker": lambda: self.start_worker("coding"),
            "api": self.start_api,
        }
        
        # Create tasks
        for component in components:
            if component in component_map:
                task = asyncio.create_task(component_map[component]())
                self.tasks.append(task)
            else:
                logger.warning(f"Unknown component: {component}")
        
        self.running = True
        
        # Wait for all tasks
        try:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        except asyncio.CancelledError:
            logger.info("Components cancelled")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down...")
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cancellations
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Cleanup
        await close_db()
        await queue_manager.disconnect()
        
        logger.info("Shutdown complete")


def signal_handler(runner: ComponentRunner):
    """Handle shutdown signals"""
    def handler(signum, frame):
        logger.info(f"Received signal {signum}")
        for task in runner.tasks:
            task.cancel()
    return handler


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="AI Money Machine")
    parser.add_argument(
        "mode",
        choices=["full", "api", "worker", "scout", "orchestrator", "evaluator", "dispatcher", "reviewer"],
        default="full",
        help="Startup mode"
    )
    
    args = parser.parse_args()
    
    runner = ComponentRunner()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, lambda s, f: asyncio.create_task(runner.shutdown()))
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(runner.shutdown()))
    
    # Determine components to run
    mode_components = {
        "full": ["evaluator", "dispatcher", "reviewer", "worker", "api"],
        "api": ["api"],
        "worker": ["worker"],
        "scout": ["scout"],
        "orchestrator": ["evaluator", "dispatcher", "reviewer"],
        "evaluator": ["evaluator"],
        "dispatcher": ["dispatcher"],
        "reviewer": ["reviewer"],
    }
    
    components = mode_components.get(args.mode, ["api"])
    
    logger.info(f"Starting AMM in '{args.mode}' mode with components: {components}")
    
    try:
        await runner.run_components(components)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await runner.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
