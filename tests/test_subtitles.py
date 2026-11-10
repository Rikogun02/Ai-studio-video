import unittest

from app.main import make_srt


class SubtitleTests(unittest.TestCase):
    def test_subtitle_has_srt_cues(self):
        result = make_srt("Kalimat pertama. Kalimat kedua.", 60)
        self.assertIn("1\n00:00:00,000 -->", result)
        self.assertIn("Kalimat pertama.", result)
        self.assertIn("Kalimat kedua.", result)

    def test_long_sentence_is_split_into_readable_chunks(self):
        words = " ".join("kata" for _ in range(25))
        result = make_srt(words, 60)
        self.assertGreaterEqual(result.count("-->"), 3)

    def test_last_caption_ends_at_requested_duration(self):
        result = make_srt("Satu kalimat.", 60)
        self.assertIn("00:01:00,000", result)


if __name__ == "__main__":
    unittest.main()
