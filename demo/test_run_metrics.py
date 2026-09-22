import json
from pathlib import Path
import tempfile
import unittest
from recording import Recorder
from run_metrics import metrics, distribution
from test_routing_trace import fixture


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.recorder = Recorder(self.root/'run', scope='synthetic', metadata={})
        self.addCleanup(self.recorder.close)

    def queue(self, task):
        self.recorder.append('task_queued', task, document_id='private-doc',
                             family_id='private-family', modality='image')

    def start(self, task):
        self.queue(task)
        self.recorder.append('request_started', task, input_sha256='a'*64, budget_reserved_usd='2')

    def response(self, task, **fields):
        self.recorder.append('response_received', task, http_status=200,
                             response_sha256='b'*64, elapsed_ms=12, **fields)

    def finish(self):
        self.recorder.close()
        return metrics(self.root/'run', self.root/'metrics.json')

    def test_route_cohorts_keep_missing_values_and_cost_scope(self):
        self.start('accepted')
        self.response('accepted', route='review', reason='accepted', routing_trace=fixture(),
                      generation_cost_usd='0.0000001', generation_input_tokens=0)
        self.recorder.append('review_validated', 'accepted', review_sha256='c'*64, finding_count=2)
        self.recorder.append('task_completed', 'accepted', outcome='review_validated')
        self.start('legacy')
        self.response('legacy', route='review')
        self.recorder.append('task_completed', 'legacy', outcome='handler_completed')
        self.queue('deferred')
        self.recorder.append('task_deferred', 'deferred', reason='budget_admission_refused')
        self.start('uncertain')
        self.recorder.append('task_uncertain', 'uncertain', error='deadline')
        report = self.finish()
        route = report['by_route'][0]
        self.assertEqual(route['tasks'], 2)
        self.assertEqual(route['timing']['decision_transport_ns'],
                         {'observed': 1, 'missing': 1, 'minimum': 2, 'maximum': 2, 'p50': 2, 'p95': 2})
        self.assertEqual(report['tasks'][0]['handler_transport_ns'], 4)
        self.assertEqual(report['tasks'][0]['tokens']['generation_input_tokens'], 0)
        self.assertIsNone(report['tasks'][1]['tokens']['generation_input_tokens'])
        self.assertEqual(report['without_observed_route']['tasks'], 2)
        self.assertIsNone(report['without_observed_route']['reported_generation_cost_usd'])
        self.assertEqual(report['summary']['reported_generation_cost_usd'], '1E-7')
        self.assertIsNone(report['summary']['total_cost_usd'])
        self.assertIsNone(report['summary']['savings_usd'])
        self.assertNotIn('private-doc', json.dumps(report))
        with self.assertRaises(FileExistsError): metrics(self.root/'run', self.root/'metrics.json')

    def test_fallback_keeps_choice_and_has_no_handler_measurement(self):
        self.start('fallback')
        trace = fixture()
        trace.update(handler_send_started_ns=None, handler_validated_ns=None)
        trace['decision'].update(confidence=.1, route='fallback', reason='uncertain')
        self.response('fallback', route='fallback', reason='uncertain', routing_trace=trace)
        self.recorder.append('task_completed', 'fallback', outcome='fallback')
        row = self.finish()['tasks'][0]
        self.assertEqual(row['decision']['choice'], 'review')
        self.assertEqual(row['route'], 'fallback')
        self.assertIsNone(row['handler_transport_ns'])

    def test_unsealed_and_tampered_inputs_produce_no_report(self):
        self.queue('task')
        with self.assertRaises(ValueError): metrics(self.root/'run', self.root/'metrics.json')
        self.recorder.close()
        path = self.root/'run'/'events.jsonl'
        path.write_bytes(path.read_bytes().replace(b'private-doc', b'changed-doc'))
        with self.assertRaises(ValueError): metrics(self.root/'run', self.root/'metrics.json')
        self.assertFalse((self.root/'metrics.json').exists())

    def test_sealed_incomplete_and_empty_runs(self):
        self.queue('pending')
        report = self.finish()
        self.assertEqual(report['summary']['states'], {'task_queued': 1})
        self.assertEqual(report['by_route'], [])
        self.assertIsNone(report['summary']['timing']['observer_request_ms']['p95'])
        empty = Recorder(self.root/'empty', scope='live', metadata={})
        empty.close()
        report = metrics(self.root/'empty', self.root/'empty-metrics.json')
        self.assertEqual(report['scope'], 'live')
        self.assertFalse(report['publication_approved'])
        self.assertEqual(report['summary']['tasks'], 0)

    def test_nearest_rank_quantiles_are_not_interpolated(self):
        result = distribution(list(range(1, 21)))
        self.assertEqual(result['p50'], 10)
        self.assertEqual(result['p95'], 19)


if __name__ == '__main__': unittest.main()
