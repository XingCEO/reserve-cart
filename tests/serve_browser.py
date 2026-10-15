import os
from pathlib import Path
import subprocess
import sys
import tempfile
with tempfile.TemporaryDirectory(prefix='reserve-cart-e2e-') as directory:
    subprocess.run([sys.executable,'-m','reserve_cart','--demo','--database',str(Path(directory)/'test.sqlite3'),'--port','5056'],env={**os.environ,'SHOP_ADMIN_PASSWORD':'browser-test-password'},check=True)
