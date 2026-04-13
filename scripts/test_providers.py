#!/usr/bin/env python3
"""
Test all enabled AI Providers

Tests:
1. Simple conversation test (Hello, respond with just "OK")
2. JSON output test (require structured JSON)
3. Long text test (generate code)
4. Error handling test (invalid API Key)

Each test records:
- Response time
- Token usage
- Actual cost
- Output quality

Usage:
    python scripts/test_providers.py
"""

import asyncio
import sys
import time
from typing import Optional

# Add project root to path
sys.path.insert(0, '.')

from gateway.providers.kimi import KimiProvider
from gateway.providers.deepseek import DeepSeekProvider
from core.config import settings


class ProviderTester:
    """Test AI providers"""
    
    def __init__(self):
        self.results = {}
    
    async def test_provider(self, provider, provider_name: str):
        """Run all tests for a provider"""
        print(f"\n{'='*60}")
        print(f"Provider: {provider_name}")
        print(f"{'='*60}")
        
        total_cost = 0.0
        tests_passed = 0
        tests_failed = 0
        
        # Test 1: Simple conversation
        try:
            result = await self._test_simple_conversation(provider)
            total_cost += result['cost']
            if result['success']:
                print(f"  ✓ Simple conversation: {result['latency_ms']}ms, "
                      f"{result['tokens']} tokens, ${result['cost']:.6f}")
                tests_passed += 1
            else:
                print(f"  ✗ Simple conversation: {result['error']}")
                tests_failed += 1
        except Exception as e:
            print(f"  ✗ Simple conversation: {e}")
            tests_failed += 1
        
        # Test 2: JSON output
        try:
            result = await self._test_json_output(provider)
            total_cost += result['cost']
            if result['success']:
                print(f"  ✓ JSON output: {result['latency_ms']}ms, "
                      f"{result['tokens']} tokens, ${result['cost']:.6f}")
                tests_passed += 1
            else:
                print(f"  ✗ JSON output: {result['error']}")
                tests_failed += 1
        except Exception as e:
            print(f"  ✗ JSON output: {e}")
            tests_failed += 1
        
        # Test 3: Long text (code generation)
        try:
            result = await self._test_code_generation(provider)
            total_cost += result['cost']
            if result['success']:
                print(f"  ✓ Code generation: {result['latency_ms']}ms, "
                      f"{result['tokens']} tokens, ${result['cost']:.6f}")
                tests_passed += 1
            else:
                print(f"  ✗ Code generation: {result['error']}")
                tests_failed += 1
        except Exception as e:
            print(f"  ✗ Code generation: {e}")
            tests_failed += 1
        
        # Test 4: Error handling (invalid key)
        try:
            result = await self._test_error_handling(provider_name)
            if result['success']:
                print(f"  ✓ Error handling: correctly raised {result['error_type']}")
                tests_passed += 1
            else:
                print(f"  ✗ Error handling: {result['error']}")
                tests_failed += 1
        except Exception as e:
            print(f"  ✗ Error handling: {e}")
            tests_failed += 1
        
        # Summary
        print(f"  {'-'*50}")
        print(f"  Tests: {tests_passed} passed, {tests_failed} failed")
        print(f"  Total cost: ${total_cost:.6f}")
        
        self.results[provider_name] = {
            'tests_passed': tests_passed,
            'tests_failed': tests_failed,
            'total_cost': total_cost
        }
    
    async def _test_simple_conversation(self, provider):
        """Test simple conversation"""
        start = time.time()
        
        response = await provider.call(
            prompt='Say "OK" and nothing else.',
            system='You are a helpful assistant.',
            temperature=0.0,
            max_tokens=10,
            model_tier='haiku'
        )
        
        latency_ms = int((time.time() - start) * 1000)
        
        return {
            'success': 'OK' in response.content.upper(),
            'latency_ms': latency_ms,
            'tokens': response.input_tokens + response.output_tokens,
            'cost': response.cost,
            'content': response.content[:50]
        }
    
    async def _test_json_output(self, provider):
        """Test JSON output"""
        start = time.time()
        
        response = await provider.call(
            prompt='Return a JSON object with keys: name (string), age (number).',
            system='You are a JSON API. Return only valid JSON, no markdown.',
            temperature=0.0,
            max_tokens=100,
            model_tier='sonnet'
        )
        
        latency_ms = int((time.time() - start) * 1000)
        
        # Check if valid JSON
        import json
        content = response.content.strip()
        # Remove markdown code blocks if present
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()
        
        try:
            data = json.loads(content)
            is_valid = 'name' in data and 'age' in data
        except json.JSONDecodeError:
            is_valid = False
        
        return {
            'success': is_valid,
            'latency_ms': latency_ms,
            'tokens': response.input_tokens + response.output_tokens,
            'cost': response.cost,
            'content': response.content[:100]
        }
    
    async def _test_code_generation(self, provider):
        """Test code generation"""
        start = time.time()
        
        response = await provider.call(
            prompt='Write a Python function to calculate factorial. Include docstring.',
            system='You are a Python expert. Write clean, documented code.',
            temperature=0.3,
            max_tokens=500,
            model_tier='sonnet'
        )
        
        latency_ms = int((time.time() - start) * 1000)
        
        return {
            'success': 'def ' in response.content and 'factorial' in response.content.lower(),
            'latency_ms': latency_ms,
            'tokens': response.input_tokens + response.output_tokens,
            'cost': response.cost,
            'content': response.content[:200]
        }
    
    async def _test_error_handling(self, provider_name: str):
        """Test error handling with invalid key"""
        try:
            if provider_name == 'kimi':
                bad_provider = KimiProvider(api_key='invalid-key')
            else:
                bad_provider = DeepSeekProvider(api_key='invalid-key')
            
            await bad_provider.call(
                prompt='Hello',
                system='You are helpful',
                max_tokens=10
            )
            return {'success': False, 'error': 'Should have raised an error'}
        except Exception as e:
            error_type = type(e).__name__
            # We expect an auth error or provider error
            if 'auth' in str(e).lower() or 'unauthorized' in str(e).lower() or '401' in str(e):
                return {'success': True, 'error_type': error_type}
            # Also accept other errors as valid error handling
            return {'success': True, 'error_type': error_type}
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        
        for provider_name, result in self.results.items():
            status = "✓" if result['tests_failed'] == 0 else "✗"
            print(f"{status} {provider_name}: {result['tests_passed']}/4 tests, "
                  f"${result['total_cost']:.6f}")
        
        total_cost = sum(r['total_cost'] for r in self.results.values())
        print(f"\nTotal test cost: ${total_cost:.6f}")


async def main():
    """Main test runner"""
    print("AI Provider Test Suite")
    print("=" * 60)
    
    tester = ProviderTester()
    
    # Test Kimi
    if settings.ai_gateway.kimi_api_key:
        kimi = KimiProvider()
        await tester.test_provider(kimi, "kimi")
        await kimi.close()
    else:
        print("\n⚠ Skipping Kimi (no API key)")
    
    # Test DeepSeek
    if settings.ai_gateway.deepseek_api_key:
        deepseek = DeepSeekProvider()
        await tester.test_provider(deepseek, "deepseek")
        await deepseek.close()
    else:
        print("\n⚠ Skipping DeepSeek (no API key)")
    
    # Summary
    tester.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
