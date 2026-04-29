#!/usr/bin/env python
"""
DDL Lineage Web Interface Launcher
Supports both basic and extended (with file upload) modes
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_requirements():
    """Check if all requirements are installed."""
    try:
        import flask
        print(f"✓ Flask {flask.__version__} found")
        return True
    except ImportError:
        print("✗ Flask not found. Installing...")
        os.system("pip install flask")
        return True


def main():
    """Main entry point."""
    print("=" * 70)
    print("  DDL Lineage Analyzer - Web Interface")
    print("  v2.0")
    print("=" * 70)
    print()
    
    # Check requirements
    if not check_requirements():
        return 1
    
    # Ask which version to run
    print("\nSelect version to run:")
    print("  1) Basic (simple analysis interface)")
    print("  2) Extended (with file upload and result export)")
    print()
    
    choice = input("Enter choice (1 or 2) [default: 1]: ").strip() or "1"
    
    try:
        if choice == "1":
            print("\n▶ Starting basic web interface...")
            from app import app
            
        elif choice == "2":
            print("\n▶ Starting extended web interface...")
            from app_extended import app
            
        else:
            print("✗ Invalid choice")
            return 1
        
        print("=" * 70)
        print("  Server running at: http://127.0.0.1:5000")
        print("  Press Ctrl+C to stop")
        print("=" * 70)
        print()
        
        app.run(debug=True, host='127.0.0.1', port=5000)
        
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped")
        return 0
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
