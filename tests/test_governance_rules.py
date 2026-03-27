"""Tests for expanded governance rules."""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.governance import ConstitutionEnforcer


class TestLanguageCompliance(unittest.TestCase):
    """LANGUAGE_COMPLIANCE must pass for EN, ID, MS, ZH and structured data."""

    def setUp(self):
        self.enforcer = ConstitutionEnforcer()

    def _check_passes(self, text: str) -> bool:
        result = self.enforcer.check(text)
        violations = [v for v in result.violations if "LANGUAGE_COMPLIANCE" in v]
        return len(violations) == 0

    def test_english_passes(self):
        text = "The property is located in the heart of the city with excellent access to public transport and shopping areas. It has three bedrooms and two bathrooms."
        self.assertTrue(self._check_passes(text))

    def test_indonesian_passes(self):
        text = "Properti ini terletak di pusat kota dengan akses yang sangat baik untuk transportasi umum dan area perbelanjaan. Rumah ini memiliki tiga kamar tidur dan dua kamar mandi."
        self.assertTrue(self._check_passes(text))

    def test_malay_passes(self):
        text = "Hartanah ini terletak di pusat bandar dengan akses yang sangat baik untuk pengangkutan awam dan kawasan membeli-belah. Rumah ini mempunyai tiga bilik tidur dan dua bilik mandi."
        self.assertTrue(self._check_passes(text))

    def test_mandarin_passes(self):
        text = "这套房产位于市中心，交通便利，购物方便。共有三间卧室和两间浴室，非常适合家庭居住。"
        self.assertTrue(self._check_passes(text))

    def test_structured_json_passes(self):
        text = '{"listings": [{"id": 1, "price": 500000}]}'
        self.assertTrue(self._check_passes(text))

    def test_random_gibberish_fails(self):
        text = "xkcd qqq zzz vvv bbb nnn mmm lll kkk jjj hhh ggg fff ddd sss aaa " * 5
        self.assertFalse(self._check_passes(text))


class TestTransitionReplyMisuse(unittest.TestCase):
    """TRANSITION_REPLY_MISUSE detects mismatched transition phrases."""

    def setUp(self):
        self.enforcer = ConstitutionEnforcer()

    def _check_passes(self, text: str) -> bool:
        result = self.enforcer.check(text)
        violations = [v for v in result.violations if "TRANSITION_REPLY_MISUSE" in v]
        return len(violations) == 0

    def test_search_transition_with_listing_content_passes(self):
        text = "Sedang mencari properti...\n\nBerikut properti yang tersedia:\n- Rumah 3 kamar tidur, harga Rp 2M, luas 120 sqm"
        self.assertTrue(self._check_passes(text))

    def test_contact_transition_with_contact_content_passes(self):
        text = "Baik, saya catat dulu...\n\nSilakan hubungi agent kami di WhatsApp 08123456789"
        self.assertTrue(self._check_passes(text))

    def test_search_transition_with_contact_content_fails(self):
        text = "Sedang mencari properti...\n\nSilakan hubungi agent kami di WhatsApp untuk informasi lebih lanjut. Nama agent: Budi."
        self.assertFalse(self._check_passes(text))

    def test_contact_transition_with_listing_content_fails(self):
        text = "Baik, saya catat dulu...\n\nBerikut properti yang tersedia:\n- Rumah harga Rp 2M, 3 bedroom, luas 120 sqm"
        self.assertFalse(self._check_passes(text))

    def test_no_transition_passes(self):
        text = "Berikut properti yang tersedia di area Jakarta Selatan dengan harga terjangkau."
        self.assertTrue(self._check_passes(text))

    def test_general_info_transition_always_passes(self):
        text = "Saya cek dulu ya...\n\nSilakan hubungi agent kami untuk info lebih lanjut."
        self.assertTrue(self._check_passes(text))

    def test_english_search_transition_with_contact_content_fails(self):
        text = "Searching for properties...\n\nPlease contact our agent via email for more details."
        self.assertFalse(self._check_passes(text))

    def test_mandarin_search_transition_with_listing_content_passes(self):
        text = "正在搜索房产...\n\n以下是可用的房产：\n- 三卧室房屋，价格200万，面积120平方米"
        self.assertTrue(self._check_passes(text))


if __name__ == "__main__":
    unittest.main()
