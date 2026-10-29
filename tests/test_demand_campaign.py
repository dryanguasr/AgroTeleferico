"""Frozen demand, paired statistics and resume integrity; no Gazebo or campaigns."""
import copy
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import demand_campaign as campaign
import analyze_demand as analysis


def config():
    return campaign.read_json(ROOT / 'config/demand_pilot.json')


def native_summary(dataset, policy='A', energy=100, comparable=True):
    summary = {key: 0 for key in campaign.SUMMARY_FIELDS}
    summary.update(schema='agro-demand-summary-v1', policy=policy,
                   status='completed' if comparable else 'completed_noncomparable',
                   comparable=comparable, completed=True,
                   orders_total=dataset['requests'], orders_delivered=dataset['requests'],
                   on_time_orders=dataset['requests'], total_useful_kg=dataset['useful_mass_kg'],
                   delivered_useful_kg=dataset['useful_mass_kg'], on_time_mass_kg=dataset['useful_mass_kg'],
                   drive_positive_J=energy, drive_absorbed_J=20, simulation_s=4000)
    return summary


class DemandGeneration(unittest.TestCase):
    def test_reproducible_independent_of_order_and_other_keys(self):
        c = config()
        expected = campaign.generate_requests(c, 24, 'alternating', 7)
        campaign.generate_requests(c, 12, 'balanced', 0)
        self.assertEqual(expected, campaign.generate_requests(c, 24, 'alternating', 7))
        changed = copy.deepcopy(c)
        changed['demand']['mass_kg'] = [1, 4, 7]
        other = campaign.generate_requests(changed, 24, 'alternating', 7)
        for before, after in zip(expected, other):
            for field in ('id', 'known_s', 'requested_s', 'deadline_s', 'origin'):
                self.assertEqual(before[field], after[field])
            self.assertAlmostEqual(before['load_s'] - 2*before['mass_kg'], after['load_s'] - 2*after['mass_kg'])

    def test_full_synthetic_matrix_and_distribution(self):
        c, rows = config(), []
        for rate in c['demand']['rates_per_hour']:
            for pattern in c['demand']['patterns']:
                for seed in range(30):
                    values = campaign.generate_requests(c, rate, pattern, seed)
                    for row in values:
                        self.assertEqual(tuple(row), campaign.DEMAND_FIELDS)
                        self.assertIn(round(row['deadline_s']-row['requested_s']), (360, 540, 720))
                        self.assertLessEqual(row['known_s'], row['requested_s'])
                        self.assertGreaterEqual(row['load_s'], 12 + 2*row['mass_kg'])
                        self.assertLessEqual(row['load_s'], 35 + 2*row['mass_kg'])
                        self.assertGreaterEqual(row['unload_s'], 12 + 2*row['mass_kg'])
                        self.assertLessEqual(row['unload_s'], 35 + 2*row['mass_kg'])
                    rows.extend(values)
        # Fixed-key deterministic regression ranges verify broad intended law,
        # not an empirical validation of agricultural arrivals.
        self.assertTrue(4000 < len(rows) < 4650, len(rows))
        self.assertAlmostEqual(sum(row['known_s'] < row['requested_s'] for row in rows)/len(rows), .3, delta=.035)
        for mass, probability in zip((2, 5, 8), (.4, .4, .2)):
            self.assertAlmostEqual(sum(row['mass_kg'] == mass for row in rows)/len(rows), probability, delta=.035)

    def test_frozen_generation_and_tamper_rejected(self):
        c = config()
        c['demand'].update(seeds=2, rates_per_hour=[24], patterns=['alternating'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign.write_json(root/'config.json', c)
            params, predictor = root/'physical.params', root/'table.csv'
            params.write_text('dt .002\n')
            predictor.write_text('up,down,positive\n0,0,0\n')
            manifest = campaign.generate_dataset(root/'config.json', root/'out', params, predictor)
            self.assertEqual((manifest['dataset_count'], manifest['planned_runs']), (2, 8))
            self.assertEqual(len(manifest['frozen_files']), 3)
            campaign.load_dataset(root/'out')
            with self.assertRaises(FileExistsError):
                campaign.generate_dataset(root/'config.json', root/'out', params, predictor)
            path = root/'out'/manifest['datasets'][0]['path']
            path.write_text(path.read_text()+'\n')
            with self.assertRaisesRegex(ValueError, 'Demand bytes changed'):
                campaign.load_dataset(root/'out')

    def test_bad_schema_and_weakened_guard_rejected(self):
        for change in ('probability', 'memory', 'horizon', 'capacity'):
            c = config()
            if change == 'probability': c['demand']['mass_probabilities'] = [.3, .3, .3]
            if change == 'memory': c['runner']['admission_gib'] = 5
            if change == 'horizon': c['dispatch']['horizon_s'] = 1800
            if change == 'capacity': c['dispatch']['capacity_kg'] = 4
            with self.subTest(change=change), self.assertRaises(ValueError):
                campaign.validate_config(c)
        c = config()
        rows = campaign.generate_requests(c, 24, 'balanced', 0)
        rows[0]['known_s'] = rows[0]['requested_s'] + 1
        with self.assertRaisesRegex(ValueError, 'chronology'):
            campaign.validate_requests(rows, c)


class TerminalIntegrity(unittest.TestCase):
    def test_recent_cim_history_preserves_actual_timestamps(self):
        history = [{'unix_s': second, 'free_gib': 10} for second in range(93, 101)]
        document = {'unix_s': 100, 'free_gib': 10, 'history': history}
        evidence = campaign.admission_from_history(document, now=100.5)
        self.assertEqual(evidence['samples'], [{'unix_s': 95, 'free_gib': 10}, {'unix_s': 100, 'free_gib': 10}])
        self.assertEqual(evidence['separation_s'], 5)
        for label, altered, now in (
            ('stale', document, 103),
            ('unseparated', dict(document, history=history[-5:]), 100.5),
            ('low_intermediate', dict(document, history=[dict(item, free_gib=5.99) if item['unix_s'] == 97 else item for item in history]), 100.5),
            ('different_latest', dict(document, free_gib=11), 100.5),
            ('unordered', dict(document, history=[history[1], history[0], *history[2:]]), 100.5),
            ('nonfinite', dict(document, history=[{'unix_s': 95, 'free_gib': math.nan}, history[-1]]), 100.5),
        ):
            with self.subTest(label=label):
                self.assertIsNone(campaign.admission_from_history(altered, now))

    def test_missing_or_insufficient_history_falls_back_to_real_sample_times(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'memory.json'
            for history in ([], [{'unix_s': 99, 'free_gib': 10}, {'unix_s': 100, 'free_gib': 10}]):
                campaign.write_json(path, {'unix_s': 100, 'free_gib': 10, 'history': history})
                def advance(seconds):
                    self.assertEqual(seconds, 5)
                    campaign.write_json(path, {'unix_s': 105, 'free_gib': 10})
                with patch('demand_campaign.time.time', return_value=105), patch('demand_campaign.time.sleep', side_effect=advance) as sleep:
                    evidence = campaign.memory_admission(path, Mock(return_value=10))
                sleep.assert_called_once_with(5)
                self.assertEqual(evidence['method'], 'two_live_reads')
                self.assertEqual([sample['unix_s'] for sample in evidence['samples']], [100, 105])

    def test_valid_history_never_sleeps(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'memory.json'
            campaign.write_json(path, {'unix_s': 100, 'free_gib': 10, 'history': [{'unix_s': second, 'free_gib': 10} for second in range(95, 101)]})
            with patch('demand_campaign.time.time', return_value=100.5), patch('demand_campaign.time.sleep') as sleep:
                self.assertEqual(campaign.memory_admission(path, Mock(return_value=10))['method'], 'recorded_CIM_history')
                sleep.assert_not_called()

    def test_explicit_limit_resume_and_complete_analysis_with_runner_double(self):
        c = config()
        c['demand'].update(seeds=1, rates_per_hour=[24], patterns=['alternating'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign.write_json(root/'config.json', c)
            (root/'physical.params').write_text('dt .002\n')
            (root/'predictor.csv').write_text('up,down,positive\n0,0,0\n')
            (root/'binary').write_bytes(b'unit-test executable double')
            campaign.generate_dataset(root/'config.json', root/'campaign', root/'physical.params', root/'predictor.csv')

            def fake_attempt(directory, command, memory, expected, settings, read_memory, rss_reader):
                (directory/'output').mkdir(parents=True)
                summary = native_summary(expected['dataset'], expected['policy'], 100-10*campaign.POLICIES.index(expected['policy']))
                campaign.write_json(directory/'output/demand_summary.json', summary)
                record = {key: expected[key] for key in ('dataset_sha256', 'binary_sha256', 'frozen_files', 'policy')}
                record.update(state='completed', exit_code=0, fatal_guard=False, errors=[], summary=summary,
                              output_sha256={'output/demand_summary.json': campaign.sha256(directory/'output/demand_summary.json')})
                campaign.write_json(directory/'run_record.json', record)
                return record

            guard_double = SimpleNamespace(read_host_memory=Mock(), tree_rss=Mock())
            with patch.dict(sys.modules, {'run_loop_guarded': guard_double}), patch('demand_campaign.run_attempt', side_effect=fake_attempt) as execute:
                first = campaign.run_campaign(root/'campaign', root/'binary', root/'memory.json', limit=2)
                self.assertEqual(first['counts'], {'completed': 2, 'failed': 0, 'pending': 2})
                self.assertEqual(execute.call_count, 2)
                second = campaign.run_campaign(root/'campaign', root/'binary', root/'memory.json', resume=True)
                self.assertEqual(second['counts'], {'completed': 4, 'failed': 0, 'pending': 0})
                self.assertEqual(execute.call_count, 4)
            result = analysis.analyze(root/'campaign', root/'analysis')
            self.assertTrue(result['all_runs_completed_comparable'])
            self.assertTrue(result['representative']['selected'])
            with (root/'analysis/comparisons.csv').open() as stream:
                values = list(csv.DictReader(stream))
            energy = next(row for row in values if row['contrast'] == 'B-A' and row['metric'] == 'drive_positive_J')
            self.assertEqual((float(energy['mean']), float(energy['ci95_low']), float(energy['ci95_high'])), (-10, -10, -10))

    def test_summary_rejects_partial_nonfinite_and_count_mismatch(self):
        dataset = {'requests': 3, 'useful_mass_kg': 15}
        good = native_summary(dataset)
        campaign.validate_summary(good, dataset, 'A')
        for field, value in [('orders_delivered', 2), ('drive_positive_J', math.nan),
                             ('policy', 'B'), ('trips', .5), ('comparable', False)]:
            broken = dict(good, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                campaign.validate_summary(broken, dataset, 'A')

    def test_resume_checks_every_output_hash_and_revision(self):
        data = {'requests': 3, 'useful_mass_kg': 15}
        expected = {'dataset': data, 'dataset_sha256': 'input', 'binary_sha256': 'binary',
                    'frozen_files': {'loop.params': 'params'}, 'policy': 'A'}
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out/'output').mkdir()
            summary = native_summary(data)
            campaign.write_json(out/'output/demand_summary.json', summary)
            record = {key: value for key, value in expected.items() if key != 'dataset'}
            record.update(state='completed', exit_code=0, summary=summary,
                          output_sha256={'output/demand_summary.json': campaign.sha256(out/'output/demand_summary.json')})
            campaign.write_json(out/'run_record.json', record)
            self.assertEqual(campaign.completed_record(out, expected), record)
            with self.assertRaisesRegex(ValueError, 'provenance'):
                campaign.completed_record(out, dict(expected, binary_sha256='changed'))
            (out/'output/demand_summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'output changed'):
                campaign.completed_record(out, expected)

    def test_low_or_stale_memory_records_failure_without_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            for index, reader in enumerate((Mock(return_value=8.99), Mock(side_effect=RuntimeError('stale')))):
                expected = {'dataset': {'requests': 0, 'useful_mass_kg': 0},
                            'dataset_sha256': 'd', 'binary_sha256': 'b', 'frozen_files': {}, 'policy': 'A'}
                with patch('demand_campaign.subprocess.Popen') as launch:
                    record = campaign.run_attempt(Path(temp)/str(index), ['not-launched'], Path(temp)/'memory.json',
                                                  expected, config()['runner'], reader, Mock())
                    launch.assert_not_called()
                self.assertTrue(record['fatal_guard'])
                self.assertEqual(record['state'], 'failed')
                self.assertTrue((Path(temp)/str(index)/'run_record.json').exists())


class PairedAnalysis(unittest.TestCase):
    def test_bootstrap_known_difference_and_reproducibility(self):
        columns = {'energy': [-2., -2., -2.], 'time': [1., 2., 3.]}
        first = analysis.bootstrap_columns(columns, ['test'], replicates=10000)
        self.assertEqual(first, analysis.bootstrap_columns(columns, ['test'], replicates=10000))
        summary = analysis.describe(columns['energy'], first['energy'])
        self.assertEqual((summary['mean'], summary['ci95_low'], summary['ci95_high']), (-2, -2, -2))
        self.assertEqual(analysis.describe([], [] )['n'], 0)

    def test_electrical_components_separate_draw_recovery_and_signed_net(self):
        self.assertEqual(analysis.electric_components({'drive_positive_J': 70, 'drive_absorbed_J': 1000, 'simulation_s': 10}, .7, 5, .5),
                         {'E_draw_J': 150, 'E_recover_J': 500, 'E_net_J': -350})

    def test_factorial_interaction_requires_all_four_same_workload(self):
        data = {'requests': 3, 'useful_mass_kg': 15}
        rows = []
        for policy, energy in zip(campaign.POLICIES, (100, 90, 80, 60)):
            summary = native_summary(data, policy, energy)
            rows.append({'seed': 0, 'policy': policy, 'comparable': True, 'summary': summary,
                         'metrics': analysis.summary_metrics(summary), 'reason': None})
        usable, excluded, columns = analysis.paired_group(rows, analysis.CONTRASTS['(D-C)-(B-A)'])
        self.assertEqual((len(usable), len(excluded), columns['drive_positive_J']), (1, 0, [-10]))
        rows[-1]['comparable'] = False
        self.assertEqual(len(analysis.paired_group(rows, analysis.CONTRASTS['(D-C)-(B-A)'])[0]), 0)
        self.assertEqual(len(analysis.paired_group(rows, analysis.CONTRASTS['B-A'])[0]), 1)

    def test_representative_uses_baseline_median_and_deterministic_tie(self):
        rows = []
        for seed, energy in enumerate((10, 30, 20)):
            for policy in campaign.POLICIES:
                rows.append({'seed': seed, 'policy': policy, 'rate_per_hour': 24, 'pattern': 'alternating',
                             'comparable': True, 'summary': {'drive_positive_J': energy},
                             'dataset': f'd{seed}', 'path': f'inputs/d{seed}/requests.csv', 'sha256': str(seed), 'attempt': f'run/{seed}/{policy}'})
        self.assertEqual(analysis.select_representative(rows, config()['analysis'])['seed'], 2)
        next(row for row in rows if row['seed'] == 2 and row['policy'] == 'C')['comparable'] = False
        self.assertEqual(analysis.select_representative(rows, config()['analysis'])['seed'], 0)

    def test_incomplete_matrix_cannot_disappear_from_analysis(self):
        c = config()
        c['demand'].update(seeds=1, rates_per_hour=[24], patterns=['alternating'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign.write_json(root/'config.json', c)
            campaign.generate_dataset(root/'config.json', root/'campaign')
            base = root/'campaign'
            manifest_hash = campaign.sha256(base/'dataset.json')
            campaign.write_json(base/'execution.json', {'dataset_manifest_sha256': manifest_hash, 'binary_sha256': 'unused'})
            dataset_id = campaign.read_json(base/'dataset.json')['datasets'][0]['id']
            report = {'dataset_manifest_sha256': manifest_hash, 'runs': [
                {'dataset': dataset_id, 'policy': policy, 'state': 'pending'} for policy in campaign.POLICIES]}
            campaign.write_json(base/'campaign.json', report)
            result = analysis.analyze(base, root/'analysis')
            self.assertEqual(result['counts'], {'completed': 0, 'failed': 0, 'pending': 4})
            self.assertFalse(result['all_runs_completed_comparable'])
            self.assertFalse(result['representative']['selected'])
            with (root/'analysis/run_metrics.csv').open() as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 4)
            report['runs'].pop()
            campaign.write_json(base/'campaign.json', report)
            with self.assertRaisesRegex(ValueError, 'every planned run'):
                analysis.collect_runs(base)


if __name__ == '__main__':
    unittest.main()
