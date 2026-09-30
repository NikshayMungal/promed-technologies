from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from storage import connect, load, save

class AppTests(unittest.TestCase):
    def test_demo_navigation(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DB_MODE':'sqlite', 'DATABASE_URL':f'sqlite:///{folder}/test.db'}):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
            self.assertFalse(app.exception)
            app.sidebar.radio[0].set_value('Import data').run()
            app.button[1].click().run()
            self.assertFalse(app.exception)
            for page in ['Overview', 'Receipt matching', 'Statements & reminders', 'Import history']:
                app.sidebar.radio[0].set_value(page).run(timeout=30)
                self.assertFalse(app.exception, page)
            app.sidebar.radio[0].set_value('Overview').run()
            self.assertEqual(app.metric[0].value, 'R 27,500.00')
    def test_snapshot_persistence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DB_MODE':'sqlite', 'DATABASE_URL':f'sqlite:///{folder}/test.db'}):
            engine, table = connect()
            save(engine, table, {'test': []}, '2026-09-30', 'test')
            self.assertEqual(load(engine, table)['label'], 'test')
            engine.dispose()
