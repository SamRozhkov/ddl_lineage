"""
ddl_lineage.__main__
====================
Command-line interface.  Run with:

    python -m ddl_lineage schema.sql
    python -m ddl_lineage schema.sql --format dot | dot -Tsvg -o lineage.svg
    python -m ddl_lineage schema.sql --impact orders
"""

import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
