"""
Freelance Scout - Discovers opportunities on freelance platforms

Phase 1 Implementation:
- Mock data mode for development
- RSS/API discovery (where available)
- Search engine indirect discovery
"""

import logging
import random
from datetime import datetime
from typing import List

from core.config import settings
from core.models import Signal, Urgency
from gateway.gateway import AIGateway
from scouts.base_scout import BaseScout

logger = logging.getLogger(__name__)


# Mock data for development
MOCK_OPPORTUNITIES = [
    {
        "source": "upwork",
        "title": "Python CLI Tool for Data Processing",
        "description": """Looking for a Python developer to create a command-line tool for processing CSV files.

Requirements:
- Read large CSV files (1GB+)
- Filter and transform data
- Output to JSON and Excel
- Progress bars and logging
- Error handling

Budget: $500-800
Timeline: 1 week""",
        "estimated_revenue": 650.0,
        "estimated_effort_hours": 20.0,
        "urgency": "medium",
        "required_skills": ["python", "pandas", "click"],
        "url": "https://upwork.com/jobs/python-cli-tool-001",
    },
    {
        "source": "upwork",
        "title": "Web Scraping Script for E-commerce",
        "description": """Need a web scraper to extract product data from e-commerce sites.

Requirements:
- Scrape product details, prices, availability
- Handle pagination and dynamic content
- Export to CSV/JSON
- Rotate proxies
- Bypass basic anti-bot measures

Budget: $400-600
Timeline: 5 days""",
        "estimated_revenue": 500.0,
        "estimated_effort_hours": 15.0,
        "urgency": "high",
        "required_skills": ["python", "scrapy", "selenium"],
        "url": "https://upwork.com/jobs/web-scraping-ecommerce-002",
    },
    {
        "source": "fiverr",
        "title": "API Integration - Stripe Payment Gateway",
        "description": """Integrate Stripe payment processing into our web application.

Requirements:
- Set up Stripe Checkout
- Handle webhooks for payment confirmation
- Implement subscription billing
- Error handling and logging
- Test mode integration

Budget: $300-500
Timeline: 3-4 days""",
        "estimated_revenue": 400.0,
        "estimated_effort_hours": 12.0,
        "urgency": "medium",
        "required_skills": ["python", "fastapi", "stripe"],
        "url": "https://fiverr.com/gigs/stripe-integration-003",
    },
    {
        "source": "upwork",
        "title": "Data Analysis Dashboard with Streamlit",
        "description": """Create an interactive dashboard for sales data visualization.

Requirements:
- Connect to PostgreSQL database
- Interactive charts and filters
- User authentication
- Export reports to PDF
- Deploy to cloud

Budget: $800-1200
Timeline: 2 weeks""",
        "estimated_revenue": 1000.0,
        "estimated_effort_hours": 30.0,
        "urgency": "low",
        "required_skills": ["python", "streamlit", "sql", "plotly"],
        "url": "https://upwork.com/jobs/streamlit-dashboard-004",
    },
    {
        "source": "fiverr",
        "title": "Automate Excel Report Generation",
        "description": """Automate monthly Excel reports from database exports.

Requirements:
- Read data from SQL exports
- Generate formatted Excel with charts
- Email distribution
- Schedule automation
- Template customization

Budget: $250-400
Timeline: 1 week""",
        "estimated_revenue": 325.0,
        "estimated_effort_hours": 10.0,
        "urgency": "medium",
        "required_skills": ["python", "pandas", "openpyxl"],
        "url": "https://fiverr.com/gigs/excel-automation-005",
    },
    {
        "source": "upwork",
        "title": "Discord Bot for Community Management",
        "description": """Build a custom Discord bot for our community server.

Requirements:
- Welcome new members
- Auto-moderation features
- Custom commands
- Integration with external API
- Logging and analytics

Budget: $600-900
Timeline: 10 days""",
        "estimated_revenue": 750.0,
        "estimated_effort_hours": 25.0,
        "urgency": "high",
        "required_skills": ["python", "discord.py", "async"],
        "url": "https://upwork.com/jobs/discord-bot-006",
    },
    {
        "source": "github",
        "title": "Open Source: CLI Task Manager",
        "description": """Contribute to open-source CLI task manager.

Features to implement:
- Task prioritization
- Due date reminders
- Project grouping
- Export to various formats
- Sync with cloud storage

This is a good project for portfolio building.""",
        "estimated_revenue": 0.0,  # Open source
        "estimated_effort_hours": 40.0,
        "urgency": "low",
        "required_skills": ["python", "cli", "git"],
        "url": "https://github.com/example/task-manager/issues/42",
    },
    {
        "source": "upwork",
        "title": "AWS Lambda Function for Image Processing",
        "description": """Create serverless functions for image resizing and optimization.

Requirements:
- Trigger on S3 upload
- Resize to multiple formats
- Compress images
- Store metadata in DynamoDB
- Error handling and retries

Budget: $500-700
Timeline: 1 week""",
        "estimated_revenue": 600.0,
        "estimated_effort_hours": 18.0,
        "urgency": "medium",
        "required_skills": ["python", "aws", "lambda", "boto3"],
        "url": "https://upwork.com/jobs/aws-lambda-images-007",
    },
    {
        "source": "fiverr",
        "title": "PDF Data Extraction Tool",
        "description": """Extract structured data from PDF invoices.

Requirements:
- Parse PDF text and tables
- Extract key fields (invoice #, amount, date)
- Handle multiple formats
- Export to Excel
- Batch processing

Budget: $350-500
Timeline: 5 days""",
        "estimated_revenue": 425.0,
        "estimated_effort_hours": 14.0,
        "urgency": "medium",
        "required_skills": ["python", "pdfplumber", "pandas"],
        "url": "https://fiverr.com/gigs/pdf-extraction-008",
    },
    {
        "source": "upwork",
        "title": "Database Migration Script",
        "description": """Migrate data from MySQL to PostgreSQL with transformations.

Requirements:
- Extract from MySQL
- Transform data types and schema
- Load to PostgreSQL
- Validate data integrity
- Handle large datasets

Budget: $700-1000
Timeline: 1 week""",
        "estimated_revenue": 850.0,
        "estimated_effort_hours": 28.0,
        "urgency": "high",
        "required_skills": ["python", "sql", "mysql", "postgresql"],
        "url": "https://upwork.com/jobs/db-migration-009",
    },
    {
        "source": "upwork",
        "title": "Slack Notification Bot",
        "description": """Build a Slack bot for team notifications from various sources.

Requirements:
- Webhook integration
- Custom notification rules
- Scheduled messages
- Interactive buttons
- Error monitoring

Budget: $400-600
Timeline: 1 week""",
        "estimated_revenue": 500.0,
        "estimated_effort_hours": 16.0,
        "urgency": "low",
        "required_skills": ["python", "slack-api", "webhooks"],
        "url": "https://upwork.com/jobs/slack-bot-010",
    },
]


class FreelanceScout(BaseScout):
    """
    Scout for freelance platforms (Upwork, Fiverr, etc.)
    
    Phase 1 uses mock data for development.
    Phase 2 will implement real platform APIs/RSS feeds.
    """
    
    SCOUT_TYPE = "freelance"
    
    def __init__(
        self,
        gateway: AIGateway = None,
        queue=None,
        config: dict = None
    ):
        super().__init__(gateway, queue, config)
        self.mock_mode = settings.ai_gateway.mock_scouts
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def scan(self) -> List[dict]:
        """
        Scan freelance platforms for opportunities
        
        Phase 1: Returns mock data
        Phase 2: Will implement RSS/API scraping
        """
        if self.mock_mode:
            self.logger.info("[MOCK] Returning mock opportunities")
            # Return 3-5 random opportunities
            count = random.randint(3, 5)
            return random.sample(MOCK_OPPORTUNITIES, count)
        
        # Phase 2: Implement real scanning
        # TODO: Implement RSS feed parsing
        # TODO: Implement search engine scraping
        self.logger.warning("Real scanning not implemented in Phase 1")
        return []
    
    async def parse(self, raw_data: List[dict]) -> List[Signal]:
        """
        Parse raw opportunities into standardized Signal format
        
        Uses Haiku to extract structured information.
        """
        signals = []
        
        for item in raw_data:
            try:
                signal = await self._parse_single(item)
                signals.append(signal)
            except Exception as e:
                self.logger.error(f"Failed to parse item: {e}")
                continue
        
        return signals
    
    async def _parse_single(self, item: dict) -> Signal:
        """Parse a single opportunity into Signal"""
        # In mock mode, directly create Signal
        if self.mock_mode:
            return self._create_mock_signal(item)
        
        # Use AI to extract structured data
        prompt = f"""Extract structured information from this job posting:

Title: {item.get('title', '')}
Description: {item.get('description', '')}

Extract and return JSON:
{{
    "skills": ["skill1", "skill2"],
    "budget_min": 0,
    "budget_max": 0,
    "urgency": "low|medium|high",
    "is_remote": true,
    "location": ""
}}"""
        
        response = await self.gateway.complete(
            prompt=prompt,
            model_tier="haiku",  # Use cheapest model for parsing
            temperature=0.3,
            max_tokens=500,
        )
        
        # Parse response
        try:
            import json
            data = json.loads(response.content)
        except:
            data = {}
        
        return Signal(
            source=item.get("source", "unknown"),
            scout_type=self.SCOUT_TYPE,
            title=item.get("title", "Untitled"),
            description=item.get("description", ""),
            estimated_revenue=item.get("estimated_revenue") or data.get("budget_max", 0),
            estimated_effort_hours=item.get("estimated_effort_hours"),
            urgency=item.get("urgency", Urgency.MEDIUM),
            required_skills=item.get("required_skills") or data.get("skills", []),
            raw_url=item.get("url", ""),
            compliance_flags=["platform_tos_check"],
            requires_human_interaction=True,  # Freelance tasks need human
            metadata={
                "raw_data": item,
                "parsed_data": data,
            },
        )
    
    def _create_mock_signal(self, item: dict) -> Signal:
        """Create Signal from mock data"""
        return Signal(
            source=item["source"],
            scout_type=self.SCOUT_TYPE,
            title=item["title"],
            description=item["description"],
            estimated_revenue=item.get("estimated_revenue"),
            estimated_effort_hours=item.get("estimated_effort_hours"),
            urgency=item.get("urgency", Urgency.MEDIUM),
            required_skills=item.get("required_skills", []),
            raw_url=item.get("url", ""),
            compliance_flags=["platform_tos_check"],
            requires_human_interaction=True,
            metadata={
                "scout_version": "phase1_mock",
                "discovered_at": datetime.utcnow().isoformat(),
            },
        )


# Celery task for scheduled scanning
from celery_app import app

@app.task
def freelance_scout_scan():
    """Celery task to run freelance scout"""
    import asyncio
    
    scout = FreelanceScout()
    asyncio.run(scout.run_once())
    
    return {"status": "completed", "scout": "freelance"}
