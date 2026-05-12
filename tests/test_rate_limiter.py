import unittest

from app.services.rate_limiter import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_allows_under_limit(self):
        limiter = RateLimiter(2, jitter_seconds=0)

        self.assertTrue(limiter.allow())

    def test_blocks_after_limit_consumed(self):
        limiter = RateLimiter(1, jitter_seconds=0)
        limiter._timestamps.append(__import__("time").monotonic())

        self.assertFalse(limiter.allow())


if __name__ == "__main__":
    unittest.main()

