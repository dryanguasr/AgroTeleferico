"""Energy ledger audit with independent synthetic telemetry and corruptions."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_demand_energy import audit_energy


class Energy(unittest.TestCase):
    def fixture(self, root):
        (root/'params').write_text('terrain 2 0 0 8.6 3.2\n')
        (root/'requests.csv').write_text('id,origin,mass_kg\nx,0,5\n')
        keys = ['time_s', 'wind_m_s', 'drive_positive_J', 'drive_absorbed_J', 'local_positive_J',
                'local_absorbed_J', 'wind_work_J', 'loss_work_J', 'load_energy_J',
                'stop_loss_J', 'energy_J', 'residual_J']
        first = dict.fromkeys(keys, 0.)
        first['energy_J'] = 1000.
        last = dict(first, time_s=200, drive_positive_J=200, drive_absorbed_J=40,
                    loss_work_J=3.04, load_energy_J=-156.96)
        summary = {k: last[k] for k in keys if k not in ('time_s', 'energy_J')}
        summary.update(energy_delta_J=0, simulation_s=200, energy_acceptance_schema='agro-demand-energy-v1',
                       energy_accepted=True, energy_residual_budget_J=2.9304, peak_abs_energy_residual_J=0,
                       completed=True, comparable=True, status='completed', governor_or_stop_count=0,
                       orders_delivered=1, delivered_useful_kg=5)
        return [first, last], summary

    def audit(self, root, rows, summary):
        with (root/'global.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (root/'demand_summary.json').write_text(json.dumps(summary))
        return audit_energy(root/'requests.csv', root, root/'params')

    def test_balanced_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows, summary = self.fixture(root)
            self.assertTrue(self.audit(root, rows, summary)['passed'])

    def test_corruptions_rejected(self):
        for case in ('ledger', 'residual', 'mass', 'terminal', 'nan', 'counter', 'scope', 'missing', 'peak', 'truncated'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                rows, summary = self.fixture(root)
                if case == 'ledger':
                    rows[-1]['residual_J'] = 1
                elif case == 'residual':
                    rows[-1]['loss_work_J'] += 20
                    rows[-1]['residual_J'] = 20
                    summary.update(loss_work_J=23.04, residual_J=20, energy_residual_budget_J=3.1304,
                                   peak_abs_energy_residual_J=20)
                elif case == 'mass':
                    (root/'requests.csv').write_text('id,origin,mass_kg\nx,1,5\n')
                elif case == 'terminal':
                    rows[-1]['energy_J'] += .2
                    rows[-1]['residual_J'] = .2
                    summary.update(energy_delta_J=.2, residual_J=.2, peak_abs_energy_residual_J=.2)
                elif case == 'nan':
                    rows[-1]['drive_positive_J'] = float('nan')
                elif case == 'counter':
                    rows[-1]['loss_work_J'] = -1
                elif case == 'scope':
                    rows[-1]['wind_m_s'] = 1
                elif case == 'missing':
                    del summary['energy_acceptance_schema']
                elif case == 'peak':
                    rows.insert(1, dict(rows[0], time_s=1, energy_J=1010, residual_J=10))
                elif case == 'truncated':
                    rows.pop()
                self.assertFalse(self.audit(root, rows, summary)['passed'])

    def test_still_air_drag_is_included_in_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows, summary = self.fixture(root)
            rows[-1].update(wind_work_J=-.2, loss_work_J=2.84)
            summary.update(wind_work_J=-.2, loss_work_J=2.84, energy_residual_budget_J=2.9284)
            self.assertTrue(self.audit(root, rows, summary)['passed'])


if __name__ == '__main__':
    unittest.main()
