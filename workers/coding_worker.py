"""
Coding Worker - Executes coding-related tasks

Features:
- Analyzes requirements and creates development plan
- Generates production-quality code
- Creates unit tests
- Generates documentation
- Packages deliverables
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from core.config import settings
from core.database import async_session_maker
from core.models import Task, TaskResult, TaskStatus
from gateway.gateway import AIGateway
from workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


@dataclass
class CodeFile:
    """Represents a generated code file"""
    path: str
    content: str
    description: str = ""


class CodingWorker(BaseWorker):
    """
    Worker for coding tasks
    
    Execution flow:
    1. Analyze requirements
    2. Check for matching Skill
    3. Generate code (or follow Skill workflow)
    4. Generate tests
    5. Generate documentation
    6. Package all files
    """
    
    QUEUE_NAME = "queue:tasks:pending"
    SUPPORTED_TASK_TYPES = ["coding", "automation", "script"]
    
    def __init__(self, gateway: AIGateway = None, queue=None, config: dict = None):
        super().__init__(gateway, queue, config)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def get_queue_name(self) -> str:
        return self.QUEUE_NAME
    
    async def execute(self, task: Task) -> TaskResult:
        """
        Execute a coding task
        
        Args:
            task: The task to execute
            
        Returns:
            TaskResult with generated code, tests, and documentation
        """
        self.logger.info(f"Executing coding task: {task.title}")
        
        start_time = time.time()
        total_cost = 0.0
        ai_calls = 0
        
        # Step 1: Parse requirements
        requirements = self._parse_requirements(task)
        
        # Step 2: Check for matching Skill
        skill = await self._find_matching_skill(task)
        
        if skill:
            self.logger.info(f"Using skill: {skill.id}")
            result = await self._execute_with_skill(task, skill)
        else:
            # Step 3-6: Generic coding flow
            self.logger.info("Using generic coding flow")
            
            # Step 3: Analyze and create dev plan
            dev_plan, cost = await self._analyze_requirements(requirements)
            total_cost += cost
            ai_calls += 1
            
            # Step 4: Generate code
            code_files, cost = await self._generate_code(requirements, dev_plan)
            total_cost += cost
            ai_calls += 1
            
            # Step 5: Generate tests
            test_files, cost = await self._generate_tests(code_files)
            total_cost += cost
            ai_calls += 1
            
            # Step 6: Generate documentation
            doc_files, cost = await self._generate_docs(code_files, requirements)
            total_cost += cost
            ai_calls += 1
            
            result = {
                "dev_plan": dev_plan,
                "code_files": [self._file_to_dict(f) for f in code_files],
                "test_files": [self._file_to_dict(f) for f in test_files],
                "doc_files": [self._file_to_dict(f) for f in doc_files],
            }
        
        execution_time = time.time() - start_time
        
        return TaskResult(
            task_id=str(task.id),
            status="completed",
            output_data=result,
            files_generated=[
                f["path"] for f in result.get("code_files", [])
            ] + [
                f["path"] for f in result.get("test_files", [])
            ] + [
                f["path"] for f in result.get("doc_files", [])
            ],
            ai_calls_count=ai_calls,
            total_cost=total_cost,
            execution_time=execution_time,
            quality_notes=self._generate_quality_notes(result),
        )
    
    def _parse_requirements(self, task: Task) -> dict:
        """Parse task requirements from input data"""
        return {
            "title": task.title,
            "description": task.input_data.get("description", ""),
            "skills": task.skill_id,
            "budget": task.estimated_cost,
        }
    
    async def _find_matching_skill(self, task: Task):
        """Find a matching skill for the task"""
        try:
            from knowledge.skills_store import SkillsStore
            store = SkillsStore()
            # This would be implemented in knowledge module
            return None
        except:
            return None
    
    async def _execute_with_skill(self, task: Task, skill):
        """Execute using a predefined skill workflow"""
        # TODO: Implement skill-based execution
        return {
            "code_files": [],
            "test_files": [],
            "doc_files": [],
        }
    
    async def _analyze_requirements(self, requirements: dict) -> tuple[dict, float]:
        """
        Step 1: Analyze requirements and create development plan
        """
        prompt = f"""You are a senior software architect. Analyze this project and create a structured development plan.

Project Requirements:
{requirements['description']}

Output a JSON development plan:
{{
    "project_summary": "One sentence summary",
    "tech_stack": ["python", "fastapi", "sqlalchemy"],
    "files_to_create": [
        {{"path": "main.py", "purpose": "Application entry point"}},
        {{"path": "models.py", "purpose": "Database models"}}
    ],
    "key_features": ["Feature 1", "Feature 2"],
    "potential_challenges": ["Challenge 1"],
    "estimated_lines_of_code": 500
}}"""
        
        response = await self.gateway.complete(
            prompt=prompt,
            model_tier="sonnet",
            system="You are a senior software architect. Output valid JSON only.",
            temperature=0.3,
            max_tokens=1500,
        )
        
        try:
            dev_plan = json.loads(response.content)
        except:
            dev_plan = {
                "project_summary": requirements.get("title", "Project"),
                "tech_stack": ["python"],
                "files_to_create": [],
                "key_features": [],
            }
        
        return dev_plan, response.cost
    
    async def _generate_code(
        self,
        requirements: dict,
        dev_plan: dict
    ) -> tuple[List[CodeFile], float]:
        """
        Step 2: Generate code based on development plan
        """
        files = []
        total_cost = 0.0
        
        # Generate each file
        for file_info in dev_plan.get("files_to_create", []):
            prompt = f"""Generate complete, production-ready code for this file.

Project: {requirements['title']}
Description: {requirements['description']}
Tech Stack: {', '.join(dev_plan.get('tech_stack', ['python']))}

File: {file_info['path']}
Purpose: {file_info.get('purpose', 'Implementation')}

Requirements:
1. Code must be complete and runnable
2. Include proper error handling
3. Add docstrings and comments
4. Follow best practices for the language
5. No TODOs or placeholders

Output ONLY the code file content, starting with the filename in a comment:
```python
# {file_info['path']}
# {file_info.get('purpose', '')}

<your code here>
```"""
            
            response = await self.gateway.complete(
                prompt=prompt,
                model_tier="sonnet",
                system="You are an expert programmer. Generate production-quality code.",
                temperature=0.3,
                max_tokens=3000,
            )
            
            total_cost += response.cost
            
            # Parse code from response
            content = self._extract_code(response.content, file_info['path'])
            
            files.append(CodeFile(
                path=file_info['path'],
                content=content,
                description=file_info.get('purpose', ''),
            ))
        
        return files, total_cost
    
    async def _generate_tests(self, code_files: List[CodeFile]) -> tuple[List[CodeFile], float]:
        """
        Step 3: Generate unit tests
        """
        # Combine all code
        all_code = "\n\n".join([f"```\n{f.content}\n```" for f in code_files])
        
        prompt = f"""Generate comprehensive unit tests for the following code.

Code to test:
{all_code}

Requirements:
1. Use pytest framework
2. Cover main functionality
3. Cover edge cases and error conditions
4. Include setup/teardown if needed
5. Add descriptive test names

Output the test file(s) in this format:
```python
# test_filename.py
<test code>
```"""
        
        response = await self.gateway.complete(
            prompt=prompt,
            model_tier="sonnet",
            system="You are a QA engineer. Generate thorough tests.",
            temperature=0.3,
            max_tokens=3000,
        )
        
        # Parse test files
        test_files = []
        # Simple parsing - in production would be more robust
        test_content = self._extract_code(response.content, "test_main.py")
        test_files.append(CodeFile(
            path="test_main.py",
            content=test_content,
            description="Unit tests",
        ))
        
        return test_files, response.cost
    
    async def _generate_docs(
        self,
        code_files: List[CodeFile],
        requirements: dict
    ) -> tuple[List[CodeFile], float]:
        """
        Step 4: Generate documentation
        """
        all_code = "\n\n".join([f"```\n{f.content}\n```" for f in code_files])
        
        prompt = f"""Generate a README.md for this project.

Project: {requirements['title']}
Description: {requirements['description']}

Code:
{all_code}

README should include:
1. Project overview
2. Installation instructions
3. Usage examples
4. Configuration options
5. API documentation (if applicable)

Output the README.md content."""
        
        response = await self.gateway.complete(
            prompt=prompt,
            model_tier="sonnet",
            system="You are a technical writer.",
            temperature=0.3,
            max_tokens=2000,
        )
        
        content = response.content
        # Remove markdown code blocks if present
        if content.startswith("```markdown"):
            content = content[11:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        doc_files = [
            CodeFile(path="README.md", content=content, description="Project documentation"),
        ]
        
        return doc_files, response.cost
    
    def _extract_code(self, response: str, default_path: str) -> str:
        """Extract code from markdown code blocks"""
        if "```" in response:
            # Try to extract from code block
            parts = response.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:  # Inside code block
                    # Remove language identifier if present
                    lines = part.split("\n")
                    if lines and (lines[0].strip() in ["python", "py", ""]):
                        return "\n".join(lines[1:]).strip()
                    return part.strip()
        return response.strip()
    
    def _file_to_dict(self, file: CodeFile) -> dict:
        """Convert CodeFile to dict"""
        return {
            "path": file.path,
            "content": file.content,
            "description": file.description,
        }
    
    def _generate_quality_notes(self, result: dict) -> str:
        """Generate quality assessment notes"""
        notes = []
        
        code_files = result.get("code_files", [])
        test_files = result.get("test_files", [])
        doc_files = result.get("doc_files", [])
        
        notes.append(f"Generated {len(code_files)} code files")
        notes.append(f"Generated {len(test_files)} test files")
        notes.append(f"Generated {len(doc_files)} documentation files")
        
        # Check for common quality indicators
        has_readme = any(f["path"].lower() == "readme.md" for f in doc_files)
        has_tests = len(test_files) > 0
        
        if has_readme and has_tests:
            notes.append("Complete package with documentation and tests")
        
        return "; ".join(notes)


# Celery task for coding worker
from celery_app import app

@app.task
def coding_worker_task(task_data: dict):
    """Celery task for coding worker"""
    import asyncio
    
    worker = CodingWorker()
    
    async def run():
        task = Task.from_dict(task_data)
        result = await worker.execute(task)
        await worker.submit_result(task, result)
        return result.to_dict()
    
    return asyncio.run(run())
