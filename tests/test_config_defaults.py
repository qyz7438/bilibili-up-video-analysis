import os
import unittest
from unittest.mock import patch

from app.config import Settings


class ConfigDefaultsTest(unittest.TestCase):
    def test_default_host_is_loopback(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
        self.assertEqual(settings.APP_HOST, '127.0.0.1')


if __name__ == '__main__':
    unittest.main()
