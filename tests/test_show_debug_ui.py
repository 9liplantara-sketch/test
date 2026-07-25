"""show_debug_ui: 学生にはデバッグUIを出さない"""
import os
import unittest
from unittest.mock import patch


class TestShowDebugUi(unittest.TestCase):
    def setUp(self):
        # 各テスト前に関連 env をクリア
        for key in ("DEBUG", "DEBUG_ENV", "ADMIN_PASSWORD", "STREAMLIT_CLOUD", "HOSTNAME"):
            os.environ.pop(key, None)

    def test_debug_off_hides_ui(self):
        from utils.settings import show_debug_ui

        with patch("utils.settings.is_cloud", return_value=False):
            self.assertFalse(show_debug_ui())

    def test_local_debug_without_password_shows_ui(self):
        from utils.settings import show_debug_ui

        os.environ["DEBUG"] = "1"
        with patch("utils.settings.is_cloud", return_value=False):
            with patch("utils.settings.get_secret_str", return_value=""):
                self.assertTrue(show_debug_ui())

    def test_cloud_debug_without_password_hides_ui(self):
        from utils.settings import show_debug_ui

        os.environ["DEBUG"] = "1"
        with patch("utils.settings.is_cloud", return_value=True):
            with patch("utils.settings.get_secret_str", return_value=""):
                self.assertFalse(show_debug_ui())

    def test_cloud_debug_requires_admin_auth(self):
        from utils.settings import show_debug_ui

        os.environ["DEBUG"] = "1"
        fake_st = type("S", (), {"session_state": {}})()

        with patch("utils.settings.is_cloud", return_value=True):
            with patch("utils.settings.get_secret_str", return_value="secret"):
                with patch("utils.settings._get_st", return_value=fake_st):
                    self.assertFalse(show_debug_ui())
                    fake_st.session_state["admin_authenticated"] = True
                    self.assertTrue(show_debug_ui())


if __name__ == "__main__":
    unittest.main()
