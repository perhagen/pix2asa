"""Allow running pix2asa as a module: python -m pix2asa [args...]"""

import sys
from .cli import main

sys.exit(main())
