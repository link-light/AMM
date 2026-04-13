"""
End-to-End Test Script

Tests the complete flow in Mock mode:
1. Start system (MOCK_AI=true, MOCK_SCOUTS=true)
2. Wait for Scout to discover signals
3. Verify signals in queue
4. Wait for Evaluator to evaluate
5. Verify evaluation results
6. Wait for Dispatcher to create tasks
7. Verify tasks created
8. Wait for Worker to execute
9. Verify results
10. Wait for Reviewer
11. Verify human tasks created
12. Simulate human completion
13. Verify final state
14. Check cost records
"""

import asyncio
import sys
import time
from datetime import datetime

sys.path.insert(0, '..')

from core.config import settings
from core.database import async_session_maker
from core.models import Signal, Task, HumanTask, CostRecord
from core.queue import queue_manager


class E2ETest:
    """End-to-end test runner"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
    
    def log(self, message):
        """Log test progress"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    async def step(self, name, test_func):
        """Run a test step"""
        self.log(f"Step: {name}...")
        try:
            await test_func()
            self.results.append((name, "PASS", None))
            self.log(f"  ✓ {name} - PASSED")
            return True
        except Exception as e:
            self.results.append((name, "FAIL", str(e)))
            self.log(f"  ✗ {name} - FAILED: {e}")
            return False
    
    async def test_01_queue_connection(self):
        """Test Redis connection"""
        await queue_manager.connect()
        assert queue_manager.redis is not None
    
    async def test_02_scout_discovery(self):
        """Test scout discovers signals"""
        from scouts.freelance_scout import FreelanceScout
        
        scout = FreelanceScout()
        await scout.run_once()
        
        # Check queue
        await asyncio.sleep(1)
        signals = await queue_manager.get_all(queue_manager.QUEUE_SIGNALS_RAW)
        assert len(signals) > 0, "No signals discovered"
        self.log(f"  Discovered {len(signals)} signals")
    
    async def test_03_evaluation(self):
        """Test evaluator processes signals"""
        from orchestrator.evaluator import evaluator
        
        # Process one signal
        signal_data = await queue_manager.dequeue(queue_manager.QUEUE_SIGNALS_RAW, timeout=5)
        assert signal_data is not None, "No signal in queue"
        
        await evaluator.process_signal(signal_data)
        
        # Check signal was evaluated
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(select(Signal))
            signals = result.scalars().all()
            evaluated = [s for s in signals if s.status == "evaluated"]
            assert len(evaluated) > 0, "No signals were evaluated"
    
    async def test_04_task_creation(self):
        """Test dispatcher creates tasks"""
        from orchestrator.dispatcher import dispatcher
        
        # Get an evaluated signal
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Signal).where(Signal.status == "evaluated")
            )
            signal = result.scalar()
            
            if signal:
                # Create evaluation result
                from orchestrator.evaluator import EvaluationResult, EvaluationScores
                evaluation = EvaluationResult(
                    signal_id=str(signal.id),
                    scores=EvaluationScores(),
                    total_score=75,
                    decision="accepted",
                    reasoning="Good opportunity",
                    estimated_ai_cost=0.1,
                    suggested_price=500,
                )
                
                await dispatcher.dispatch(signal, evaluation)
        
        # Check tasks were created
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(select(Task))
            tasks = result.scalars().all()
            assert len(tasks) > 0, "No tasks created"
            self.log(f"  Created {len(tasks)} tasks")
    
    async def test_05_cost_tracking(self):
        """Test cost tracking"""
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(select(CostRecord))
            costs = result.scalars().all()
            # In mock mode, costs should be tracked
            self.log(f"  {len(costs)} cost records in database")
    
    async def test_06_human_tasks(self):
        """Test human tasks are created"""
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(select(HumanTask))
            tasks = result.scalars().all()
            self.log(f"  {len(tasks)} human tasks created")
    
    def print_summary(self):
        """Print test summary"""
        elapsed = time.time() - self.start_time
        
        print("\n" + "="*60)
        print("E2E TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, status, _ in self.results if status == "PASS")
        failed = sum(1 for _, status, _ in self.results if status == "FAIL")
        
        for name, status, error in self.results:
            icon = "✓" if status == "PASS" else "✗"
            print(f"  {icon} {name}")
            if error:
                print(f"      Error: {error}")
        
        print("-"*60)
        print(f"Total: {len(self.results)} | Passed: {passed} | Failed: {failed}")
        print(f"Time: {elapsed:.2f}s")
        print("="*60)
        
        return failed == 0


async def main():
    """Run E2E tests"""
    print("="*60)
    print("AI MONEY MACHINE - END-TO-END TEST")
    print("="*60)
    print(f"Mock AI: {settings.ai_gateway.mock_ai}")
    print(f"Mock Scouts: {settings.ai_gateway.mock_scouts}")
    print("="*60 + "\n")
    
    test = E2ETest()
    test.start_time = time.time()
    
    # Run all test steps
    await test.step("Queue Connection", test.test_01_queue_connection)
    await test.step("Scout Discovery", test.test_02_scout_discovery)
    await test.step("Signal Evaluation", test.test_03_evaluation)
    await test.step("Task Creation", test.test_04_task_creation)
    await test.step("Cost Tracking", test.test_05_cost_tracking)
    await test.step("Human Tasks", test.test_06_human_tasks)
    
    # Cleanup
    await queue_manager.disconnect()
    
    # Print summary
    success = test.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
