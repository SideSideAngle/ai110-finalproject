import os
import tempfile

# Keep test runs out of the real logs/ directory. Must be set before src is imported.
os.environ.setdefault("RECOMMENDER_LOG_DIR", tempfile.mkdtemp(prefix="recommender-test-logs-"))
