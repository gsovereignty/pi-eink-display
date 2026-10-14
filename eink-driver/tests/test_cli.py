import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eink_driver.cli import main, validate_inspection
from eink_driver.config import Config


class CliTest(unittest.TestCase):
    def test_dry_run_no_transport_or_inventory(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('eink_driver.cli.live_transport', side_effect=AssertionError('hardware')), \
             patch('eink_driver.cli.mock_transport', side_effect=AssertionError('commands')), \
             patch('eink_driver.cli.inventory', side_effect=AssertionError('inventory')), \
             contextlib.redirect_stdout(io.StringIO()):
            directory = Path(tmp) / 'dry'
            self.assertEqual(main(['dry-run', '--output', str(directory)]), 0)
            self.assertEqual((directory/'frame.bin').stat().st_size, 15000)
            self.assertEqual((directory/'cs1.bin').stat().st_size, 7500)
            self.assertEqual((directory/'cs2.bin').stat().st_size, 7500)
            self.assertTrue((directory/'expected.png').is_file())
            self.assertFalse((directory/'events.jsonl').exists())
            self.assertEqual(json.loads((directory/'result.json').read_text())['hardware_status'], 'NOT RUN')

    def test_mock_exactly_one_refresh_no_live_access(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('eink_driver.cli.live_transport', side_effect=AssertionError('hardware')), \
             contextlib.redirect_stdout(io.StringIO()):
            directory = Path(tmp)/'mock'
            self.assertEqual(main(['mock', '--output', str(directory)]), 0)
            record = json.loads((directory/'result.json').read_text())
            self.assertEqual(record['refresh_count'], 1)
            self.assertEqual(record['hardware_status'], 'NOT RUN')
            self.assertTrue(record['software_completed'])

    def test_preflight_never_opens_transport(self):
        record = {'checks': {'spi': 'PASS'}}
        with patch('eink_driver.cli.inventory', return_value=record) as inspect, \
             patch('eink_driver.cli.live_transport', side_effect=AssertionError('hardware')), \
             patch('eink_driver.cli.mock_transport', side_effect=AssertionError('commands')), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['preflight']), 0)
            inspect.assert_called_once()

    def test_missing_inspection_and_047_stop_before_gpio(self):
        for args in ([], ['--resistor', '0.47']):
            with tempfile.TemporaryDirectory() as tmp, \
                 patch('eink_driver.cli.live_transport', side_effect=AssertionError('hardware')) as transport, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['smoke', '--output', str(Path(tmp)/'blocked')] + args), 1)
                transport.assert_not_called()

    def test_inspection_requires_real_date_and_observer(self):
        fields = ('all_power_disconnected_during_inspection', 'ribbon_seated_contacts_checked',
                  'wiring_matches_table', 'fan_preserved', 'no_visible_damage', 'no_abnormal_heating')
        record = dict.fromkeys(fields, True)
        record.update(resistor='3', observer='Observer', confirmed_at='2026-10-08T15:00:00+08:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'inspection.json'
            path.write_text(json.dumps(record))
            self.assertEqual(validate_inspection(path, Config()), record)
            record['confirmed_at'] = '2026-10-08T15:00:00'
            path.write_text(json.dumps(record))
            with self.assertRaises(ValueError): validate_inspection(path, Config())
