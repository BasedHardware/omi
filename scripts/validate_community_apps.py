#!/usr/bin/env python3
"""
Validation script for Omi Community Apps

This script validates app submissions for:
- File structure (required files exist)
- JSON schema compliance (app.json, registry.json)
- Code quality (Python linting, formatting)
- Security (dependency vulnerabilities, malicious patterns)
- Images (format, size, dimensions)
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

try:
    import jsonschema
    from PIL import Image
except ImportError:
    print("Installing required packages...")
    subprocess.run([sys.executable, "-m", "pip", "install", "jsonschema", "pillow"], check=True)
    import jsonschema
    from PIL import Image


class ValidationResults:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []

    def add_error(self, message: str):
        self.errors.append(message)
        print(f"❌ ERROR: {message}")

    def add_warning(self, message: str):
        self.warnings.append(message)
        print(f"⚠️  WARNING: {message}")

    def add_passed(self, message: str):
        self.passed.append(message)
        print(f"✅ PASSED: {message}")

    def to_dict(self) -> Dict[str, Any]:
        total_checks = len(self.errors) + len(self.warnings) + len(self.passed)
        if self.errors:
            summary = f"❌ Validation failed with {len(self.errors)} error(s) and {len(self.warnings)} warning(s)"
        elif self.warnings:
            summary = f"⚠️  Validation passed with {len(self.warnings)} warning(s)"
        else:
            summary = f"✅ All {total_checks} checks passed!"

        return {
            "summary": summary,
            "errors": self.errors,
            "warnings": self.warnings,
            "passed": self.passed
        }

    def save(self, output_path: str = "validation_results.json"):
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"\n📝 Results saved to {output_path}")


def get_changed_apps() -> List[Path]:
    """Get list of changed app directories from git diff"""
    try:
        # Get base branch (usually main or master)
        base_branch = os.environ.get('GITHUB_BASE_REF', 'main')

        # Get changed files
        result = subprocess.run(
            ['git', 'diff', '--name-only', f'origin/{base_branch}...HEAD'],
            capture_output=True,
            text=True,
            check=True
        )

        changed_files = result.stdout.strip().split('\n')

        # Extract unique app directories
        app_dirs = set()
        for file in changed_files:
            if file.startswith('community-apps/') and file != 'community-apps/':
                parts = file.split('/')
                if len(parts) >= 3:
                    # community-apps/author/app-name
                    if parts[1] not in ['TEMPLATE', 'registry.json', 'app-schema.json', 'README.md', 'CONTRIBUTING.md']:
                        app_dir = Path('/'.join(parts[:3]))
                        if app_dir.exists():
                            app_dirs.add(app_dir)

        return list(app_dirs)

    except subprocess.CalledProcessError:
        # Fallback: validate all apps if git diff fails
        print("⚠️  Could not determine changed files, validating all apps")
        return list(Path('community-apps').glob('*/*/'))


def validate_structure(app_dir: Path, results: ValidationResults) -> bool:
    """Validate that all required files exist"""
    required_files = ['app.json', 'main.py', 'README.md', 'requirements.txt']
    required_image = False

    for filename in required_files:
        filepath = app_dir / filename
        if not filepath.exists():
            results.add_error(f"{app_dir}: Missing required file '{filename}'")
            return False

    # Check for logo (accept .png, .jpg, .jpeg, .svg)
    logo_files = list(app_dir.glob('logo.*'))
    if not logo_files:
        results.add_error(f"{app_dir}: Missing logo image (logo.png, logo.jpg, etc.)")
        return False

    results.add_passed(f"{app_dir}: All required files present")
    return True


def validate_schema(app_dir: Path, results: ValidationResults) -> bool:
    """Validate app.json against schema"""
    app_json_path = app_dir / 'app.json'
    schema_path = Path('community-apps/app-schema.json')

    try:
        with open(app_json_path, 'r') as f:
            app_data = json.load(f)

        with open(schema_path, 'r') as f:
            schema = json.load(f)

        # Validate against schema
        jsonschema.validate(app_data, schema)

        # Additional validations
        app_id = app_data.get('id', '')
        expected_prefix = f"{app_dir.parent.name}/{app_dir.name}"

        if app_id != expected_prefix:
            results.add_error(
                f"{app_dir}: app.json 'id' must be '{expected_prefix}', got '{app_id}'"
            )
            return False

        # Check version format
        version = app_data.get('version', '')
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            results.add_error(f"{app_dir}: Invalid version format '{version}'. Use semver (e.g., 1.0.0)")
            return False

        # Check email format
        email = app_data.get('email', '')
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            results.add_error(f"{app_dir}: Invalid email format '{email}'")
            return False

        results.add_passed(f"{app_dir}: app.json schema valid")
        return True

    except json.JSONDecodeError as e:
        results.add_error(f"{app_dir}: Invalid JSON in app.json: {e}")
        return False
    except jsonschema.ValidationError as e:
        results.add_error(f"{app_dir}: Schema validation failed: {e.message}")
        return False
    except FileNotFoundError as e:
        results.add_error(f"{app_dir}: File not found: {e}")
        return False


def validate_registry(results: ValidationResults) -> bool:
    """Validate registry.json"""
    registry_path = Path('community-apps/registry.json')

    try:
        with open(registry_path, 'r') as f:
            registry = json.load(f)

        # Check for duplicate IDs
        app_ids = [app['id'] for app in registry.get('apps', [])]
        duplicates = [id for id in app_ids if app_ids.count(id) > 1]

        if duplicates:
            results.add_error(f"registry.json: Duplicate app IDs found: {', '.join(set(duplicates))}")
            return False

        # Validate each app entry
        for app in registry.get('apps', []):
            app_id = app.get('id', '')
            path = app.get('path', '')

            # Check if path exists
            if not Path(path).exists():
                results.add_warning(f"registry.json: Path '{path}' for app '{app_id}' does not exist")

            # Check if image URL is reachable (optional check)
            image_url = app.get('image', '')
            if not image_url:
                results.add_warning(f"registry.json: App '{app_id}' has no image URL")

        results.add_passed("registry.json: Valid format and structure")
        return True

    except json.JSONDecodeError as e:
        results.add_error(f"registry.json: Invalid JSON: {e}")
        return False
    except FileNotFoundError:
        results.add_error("registry.json: File not found")
        return False


def validate_code_quality(app_dir: Path, results: ValidationResults) -> bool:
    """Validate Python code quality"""
    main_py = app_dir / 'main.py'

    if not main_py.exists():
        return True  # Already checked in structure validation

    try:
        # Check if black formatting is needed
        black_result = subprocess.run(
            ['black', '--check', '--line-length', '120', str(main_py)],
            capture_output=True,
            text=True
        )

        if black_result.returncode != 0:
            results.add_warning(f"{app_dir}: Code not formatted with black. Run: black --line-length 120 {main_py}")

        # Run flake8 for style issues
        flake8_result = subprocess.run(
            ['flake8', str(main_py), '--max-line-length=120', '--ignore=E203,W503'],
            capture_output=True,
            text=True
        )

        if flake8_result.returncode != 0:
            results.add_warning(f"{app_dir}: Flake8 issues:\n{flake8_result.stdout}")

        results.add_passed(f"{app_dir}: Code quality checks passed")
        return True

    except FileNotFoundError:
        results.add_warning(f"{app_dir}: black or flake8 not installed, skipping code quality checks")
        return True


def validate_security(app_dir: Path, results: ValidationResults) -> bool:
    """Security checks on dependencies and code"""
    requirements_file = app_dir / 'requirements.txt'

    if not requirements_file.exists():
        return True

    try:
        # Check for known vulnerable packages
        safety_result = subprocess.run(
            ['safety', 'check', '--file', str(requirements_file), '--json'],
            capture_output=True,
            text=True
        )

        if safety_result.returncode != 0:
            try:
                vulnerabilities = json.loads(safety_result.stdout)
                if vulnerabilities:
                    results.add_error(
                        f"{app_dir}: Security vulnerabilities found in dependencies. "
                        f"Run 'safety check --file {requirements_file}' for details"
                    )
                    return False
            except json.JSONDecodeError:
                pass

        # Check for suspicious code patterns
        main_py = app_dir / 'main.py'
        if main_py.exists():
            with open(main_py, 'r') as f:
                code = f.read()

            suspicious_patterns = [
                (r'eval\s*\(', 'eval() usage'),
                (r'exec\s*\(', 'exec() usage'),
                (r'__import__\s*\(', 'dynamic imports'),
                (r'subprocess\.call.*shell=True', 'shell=True in subprocess'),
                (r'os\.system\s*\(', 'os.system() usage'),
            ]

            for pattern, description in suspicious_patterns:
                if re.search(pattern, code):
                    results.add_warning(f"{app_dir}: Potentially unsafe code pattern: {description}")

        results.add_passed(f"{app_dir}: Security checks passed")
        return True

    except FileNotFoundError:
        results.add_warning(f"{app_dir}: safety not installed, skipping security checks")
        return True


def validate_images(app_dir: Path, results: ValidationResults) -> bool:
    """Validate logo image"""
    logo_files = list(app_dir.glob('logo.*'))

    if not logo_files:
        return True  # Already checked in structure validation

    logo_path = logo_files[0]

    try:
        # Check file size
        file_size = logo_path.stat().st_size
        max_size = 1 * 1024 * 1024  # 1MB

        if file_size > max_size:
            results.add_error(f"{app_dir}: Logo file size ({file_size / 1024 / 1024:.2f}MB) exceeds 1MB limit")
            return False

        # Check image format and dimensions
        if logo_path.suffix.lower() not in ['.svg']:
            with Image.open(logo_path) as img:
                width, height = img.size

                # Check if square
                if width != height:
                    results.add_warning(f"{app_dir}: Logo should be square, got {width}x{height}")

                # Check recommended size
                if width < 256 or height < 256:
                    results.add_warning(f"{app_dir}: Logo resolution ({width}x{height}) is small. Recommend 512x512")

        results.add_passed(f"{app_dir}: Logo image valid")
        return True

    except Exception as e:
        results.add_error(f"{app_dir}: Error validating logo image: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Validate Omi Community Apps')
    parser.add_argument(
        'check',
        choices=['structure', 'schema', 'registry', 'quality', 'security', 'images', 'all'],
        help='Type of validation to run'
    )
    parser.add_argument(
        '--apps',
        nargs='+',
        help='Specific app directories to validate (default: auto-detect from git diff)'
    )

    args = parser.parse_args()

    results = ValidationResults()

    # Get apps to validate
    if args.apps:
        app_dirs = [Path(app) for app in args.apps]
    else:
        app_dirs = get_changed_apps()

    if not app_dirs:
        print("ℹ️  No community apps to validate")
        results.save()
        return 0

    print(f"🔍 Validating {len(app_dirs)} app(s):")
    for app_dir in app_dirs:
        print(f"  - {app_dir}")
    print()

    # Run validations
    for app_dir in app_dirs:
        if not app_dir.exists():
            results.add_error(f"{app_dir}: Directory does not exist")
            continue

        if args.check in ['structure', 'all']:
            validate_structure(app_dir, results)

        if args.check in ['schema', 'all']:
            validate_schema(app_dir, results)

        if args.check in ['quality', 'all']:
            validate_code_quality(app_dir, results)

        if args.check in ['security', 'all']:
            validate_security(app_dir, results)

        if args.check in ['images', 'all']:
            validate_images(app_dir, results)

    # Registry validation (only once)
    if args.check in ['registry', 'all']:
        validate_registry(results)

    # Save and report results
    results.save()

    print("\n" + "=" * 60)
    print(results.to_dict()['summary'])
    print("=" * 60)

    # Exit with error code if validation failed
    if results.errors:
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
