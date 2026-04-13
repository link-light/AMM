"""
Seed Data Script

Generates test data for development:
- 5 mock signals (different statuses)
- 3 mock tasks (different stages)
- 2 mock human tasks
- 1 sample skill
- 7 days of cost data
"""

import asyncio
import random
from datetime import datetime, timedelta
from uuid import uuid4

import sys
sys.path.insert(0, '..')

from core.config import settings
from core.database import async_session_maker, init_db
from core.models import (
    CostRecord,
    HumanTask,
    HumanTaskStatus,
    Signal,
    SignalStatus,
    Skill,
    SkillStatus,
    Task,
    TaskStatus,
    TaskType,
)


async def seed_signals(session):
    """Create sample signals"""
    signals = [
        Signal(
            id=uuid4(),
            source="upwork",
            scout_type="freelance",
            title="Python Web Scraper for E-commerce",
            description="Need to scrape product data from various e-commerce sites",
            estimated_revenue=500.0,
            estimated_effort_hours=15.0,
            urgency="medium",
            required_skills=["python", "scrapy"],
            raw_url="https://upwork.com/jobs/001",
            score=75.0,
            status=SignalStatus.ACCEPTED,
            requires_human_interaction=True,
            compliance_flags=["platform_tos_check"],
            metadata={"evaluation": {"decision": "accepted", "estimated_ai_cost": 0.15}},
        ),
        Signal(
            id=uuid4(),
            source="fiverr",
            scout_type="freelance",
            title="API Integration Project",
            description="Integrate Stripe payments into existing app",
            estimated_revenue=350.0,
            estimated_effort_hours=10.0,
            urgency="high",
            required_skills=["python", "fastapi", "stripe"],
            raw_url="https://fiverr.com/gigs/002",
            score=62.0,
            status=SignalStatus.EVALUATED,
            requires_human_interaction=True,
            compliance_flags=[],
            metadata={"evaluation": {"decision": "pending"}},
        ),
        Signal(
            id=uuid4(),
            source="upwork",
            scout_type="freelance",
            title="Data Analysis Dashboard",
            description="Create interactive dashboard with Streamlit",
            estimated_revenue=800.0,
            estimated_effort_hours=25.0,
            urgency="low",
            required_skills=["python", "streamlit", "pandas"],
            raw_url="https://upwork.com/jobs/003",
            score=45.0,
            status=SignalStatus.EVALUATED,
            requires_human_interaction=True,
            compliance_flags=[],
            metadata={"evaluation": {"decision": "rejected"}},
        ),
        Signal(
            id=uuid4(),
            source="github",
            scout_type="open_source",
            title="CLI Tool Enhancement",
            description="Add new features to open source CLI tool",
            estimated_revenue=0.0,
            estimated_effort_hours=20.0,
            urgency="low",
            required_skills=["python", "cli"],
            raw_url="https://github.com/example/issue/004",
            status=SignalStatus.RAW,
            requires_human_interaction=False,
            compliance_flags=[],
            metadata={},
        ),
        Signal(
            id=uuid4(),
            source="upwork",
            scout_type="freelance",
            title="Discord Bot Development",
            description="Custom bot for community management",
            estimated_revenue=600.0,
            estimated_effort_hours=18.0,
            urgency="medium",
            required_skills=["python", "discord.py"],
            raw_url="https://upwork.com/jobs/005",
            score=80.0,
            status=SignalStatus.COMPLETED,
            requires_human_interaction=True,
            compliance_flags=[],
            metadata={"completed_at": datetime.utcnow().isoformat()},
        ),
    ]
    
    for signal in signals:
        session.add(signal)
    
    await session.commit()
    print(f"Created {len(signals)} signals")
    return signals


async def seed_tasks(session, signals):
    """Create sample tasks"""
    tasks = [
        Task(
            id=uuid4(),
            signal_id=signals[0].id,
            title="Analyze requirements for web scraper",
            task_type=TaskType.RESEARCH,
            status=TaskStatus.COMPLETED,
            priority="normal",
            input_data={"description": "Research target websites"},
            actual_cost=0.05,
        ),
        Task(
            id=uuid4(),
            signal_id=signals[0].id,
            title="Develop web scraper",
            task_type=TaskType.CODING,
            status=TaskStatus.RUNNING,
            priority="high",
            input_data={"description": "Implement scraper with Scrapy"},
            estimated_cost=0.10,
        ),
        Task(
            id=uuid4(),
            signal_id=signals[1].id,
            title="Submit proposal on Fiverr",
            task_type=TaskType.HUMAN,
            status=TaskStatus.PENDING,
            priority="high",
            input_data={"description": "Submit custom offer"},
            estimated_cost=0.0,
        ),
    ]
    
    for task in tasks:
        session.add(task)
    
    await session.commit()
    print(f"Created {len(tasks)} tasks")
    return tasks


async def seed_human_tasks(session, tasks):
    """Create sample human tasks"""
    human_tasks = [
        HumanTask(
            id=uuid4(),
            task_id=tasks[2].id,
            task_type="submit_proposal",
            platform="fiverr",
            priority="high",
            status=HumanTaskStatus.PENDING,
            prepared_materials={
                "proposal_text": "I can help you integrate Stripe payments...",
                "price": "$350",
                "delivery_time": "3 days",
            },
            instructions="Submit the prepared proposal on Fiverr. Target URL included.",
            target_url="https://fiverr.com/orders/123",
            deadline=datetime.utcnow() + timedelta(days=1),
        ),
        HumanTask(
            id=uuid4(),
            task_id=tasks[2].id,
            task_type="submit_proposal",
            platform="upwork",
            priority="normal",
            status=HumanTaskStatus.PENDING,
            prepared_materials={
                "cover_letter": "I have 5+ years experience with Python and web scraping...",
            },
            instructions="Submit proposal on Upwork using the cover letter provided.",
            target_url="https://upwork.com/jobs/apply/456",
            deadline=datetime.utcnow() + timedelta(days=2),
        ),
    ]
    
    for ht in human_tasks:
        session.add(ht)
    
    await session.commit()
    print(f"Created {len(human_tasks)} human tasks")


async def seed_skills(session):
    """Create sample skill"""
    skill = Skill(
        id="upwork-python-web-scraping",
        name="Python Web Scraping for Upwork",
        version="1.0",
        category="web_scraping",
        status=SkillStatus.ACTIVE,
        success_rate=0.85,
        avg_revenue=450.0,
        avg_ai_cost=0.12,
        avg_time_hours=12.0,
        execution_count=12,
        triggers={
            "source": "upwork",
            "keywords": ["scraping", "crawler", "spider"],
            "min_budget": 300,
        },
        compliance={
            "tos_compliant": True,
            "auto_executable": True,
        },
        workflow={
            "steps": [
                {"name": "analyze_site", "type": "auto"},
                {"name": "implement_scraper", "type": "auto"},
                {"name": "test_scraper", "type": "auto"},
            ]
        },
        quality_checklist=[
            "Handles pagination",
            "Respects robots.txt",
            "Includes error handling",
        ],
    )
    
    session.add(skill)
    await session.commit()
    print("Created 1 skill")


async def seed_costs(session):
    """Create sample cost records for last 7 days"""
    providers = ["anthropic"]
    models = ["claude-sonnet-4-6", "claude-haiku-4-5"]
    tiers = ["sonnet", "haiku"]
    
    for i in range(7):
        date = datetime.utcnow() - timedelta(days=i)
        
        # Create 5-10 cost records per day
        for _ in range(random.randint(5, 10)):
            cost = CostRecord(
                id=uuid4(),
                provider=random.choice(providers),
                model=random.choice(models),
                model_tier=random.choice(tiers),
                input_tokens=random.randint(500, 3000),
                output_tokens=random.randint(200, 1500),
                cost=random.uniform(0.01, 0.15),
                latency_ms=random.randint(500, 3000),
                created_at=date,
            )
            session.add(cost)
    
    await session.commit()
    print("Created cost records for last 7 days")


async def main():
    """Main seed function"""
    print("Seeding database with test data...")
    
    # Initialize DB
    await init_db()
    
    async with async_session_maker() as session:
        # Seed in order
        signals = await seed_signals(session)
        tasks = await seed_tasks(session, signals)
        await seed_human_tasks(session, tasks)
        await seed_skills(session)
        await seed_costs(session)
    
    print("\nSeed completed successfully!")
    print("You can now start the system with: make dev")


if __name__ == "__main__":
    asyncio.run(main())
