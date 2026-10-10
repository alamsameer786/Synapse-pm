#!/usr/bin/env python
"""
Production-grade test runner with comprehensive options
"""
import sys
import pytest
import argparse
import os
from typing import List

def get_pytest_args(args) -> List[str]:
    """Generate pytest arguments based on input"""
    pytest_args = [
        "-v",
        "--tb=short",
        "--strict-markers",
        "--disable-warnings",
        "--cov=app",
        "--cov-report=html",
        "--cov-report=term",
        "--cov-report=xml",
        "--maxfail=1",
        "-p", "no:cacheprovider"  # Disable cache for clean runs
    ]
    
    # Test selection
    if args.unit:
        pytest_args.extend(["-m", "unit"])
    elif args.integration:
        pytest_args.extend(["-m", "integration"])
    elif args.security:
        pytest_args.extend(["-m", "security"])
    elif args.smoke:
        pytest_args.extend(["-m", "smoke"])
    
    # Parallel execution
    if args.parallel:
        pytest_args.extend(["-n", str(args.parallel)])
    
    # Specific test path
    if args.path:
        pytest_args.append(args.path)
    else:
        pytest_args.append("tests/")
    
    # Additional options
    if args.failfast:
        pytest_args.append("--maxfail=1")
    
    if args.no_cov:
        pytest_args = [arg for arg in pytest_args if not arg.startswith("--cov")]
    
    return pytest_args

def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description="Run tests with comprehensive options")
    
    # Test selection
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--security", action="store_true", help="Run only security tests")
    parser.add_argument("--smoke", action="store_true", help="Run only smoke tests")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    
    # Execution options
    parser.add_argument("--parallel", type=int, help="Number of parallel workers")
    parser.add_argument("--failfast", action="store_true", help="Stop on first failure")
    parser.add_argument("--no-cov", action="store_true", help="Disable coverage report")
    parser.add_argument("--path", help="Specific test file or directory")
    
    # Performance options
    parser.add_argument("--duration", action="store_true", help="Show test duration")
    parser.add_argument("--durations", type=int, default=0, help="Show N slowest tests")
    
    args = parser.parse_args()
    
    # Default to all tests if no selection
    if not any([args.unit, args.integration, args.security, args.smoke, args.all]):
        args.all = True
    
    # Set environment for testing
    os.environ["TESTING"] = "True"
    os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    
    # Get pytest arguments
    pytest_args = get_pytest_args(args)
    
    # Add duration reporting
    if args.duration or args.durations > 0:
        pytest_args.append("--durations=" + str(args.durations if args.durations > 0 else 10))
    
    # Run tests
    print(f"Running tests with: {' '.join(pytest_args)}")
    exit_code = pytest.main(pytest_args)
    
    # Generate coverage report if enabled
    if not args.no_cov and exit_code == 0:
        print("\n✅ All tests passed!")
        print("📊 Coverage report generated in htmlcov/index.html")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())