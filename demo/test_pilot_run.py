import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock
import test_pilot_plan as plan_fixture
from budget import Budget
from pilot_run import execute,preflight,child_environment,BINARIES,readiness
from recording import canonical


class Process:
    def __init__(self):self.stopped=False
    def poll(self):return 0 if self.stopped else None
    def terminate(self):self.stopped=True
    def kill(self):self.stopped=True
    def wait(self,timeout):return 0


class PilotRunTests(unittest.TestCase):
    def setUp(self):
        plan_fixture.PilotPlanTests.setUp(self)
        plan_fixture.PilotPlanTests.make(self)
        self.binaries=self.root/'bin';self.binaries.mkdir()
        for name in BINARIES:
            path=self.binaries/name;path.write_bytes(b'coordinator test placeholder; never executed');path.chmod(0o700)
        self.env={'PATH':os.environ['PATH'],'TYPESAFE_API_KEY':'test-typesafe','OPENROUTER_API_KEY':'test-openrouter',
                  'API_KEY':'must-not-leak','HTTP_PROXY':'must-not-leak','UNRELATED_SECRET':'must-not-leak'}

    def test_readiness_never_accesses_credentials_starts_services_or_claims_plan(self):
        output=self.root/'readiness.json'
        before={p.name:p.read_bytes() for p in self.output.iterdir()}
        with patch.dict(os.environ,{},clear=True),patch('pilot_run.ports_available') as ports, \
             patch('pilot_run.subprocess.run') as commands,patch('pilot_run.subprocess.Popen') as processes:
            report=readiness(self.output,self.binaries,output)
        ports.assert_not_called();commands.assert_not_called();processes.assert_not_called()
        self.assertEqual(report['status'],'offline_preflight_passed_not_authorized')
        self.assertEqual(report['total_reservation_usd'],'0.06422')
        self.assertIsNone(report['selected_allowance_usd'])
        self.assertEqual(set(report['binary_sha256']),set(BINARIES))
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.output.iterdir()})
        self.assertEqual(output.stat().st_mode & 0o777,0o600)
        with self.assertRaises(FileExistsError):readiness(self.output,self.binaries,output)

    def test_readiness_rejects_claimed_plan_and_output_inside_plan(self):
        with self.assertRaises(ValueError):readiness(self.output,self.binaries,self.output/'readiness.json')
        self.assertFalse((self.output/'readiness.json').exists())
        (self.output/'execution.json').write_bytes(b'claimed')
        with self.assertRaises(ValueError):readiness(self.output,self.binaries,self.root/'readiness.json')
        self.assertFalse((self.root/'readiness.json').exists())

    def test_child_environment_has_only_its_credential(self):
        with patch.dict(os.environ,self.env,clear=True):
            plain=child_environment();generation=child_environment('OPENROUTER_API_KEY','test-openrouter')
        self.assertEqual(plain,{'PATH':self.env['PATH']})
        self.assertEqual(set(generation),{'PATH','OPENROUTER_API_KEY'})

    def test_insufficient_allowance_and_existing_state_refuse_preflight(self):
        with self.assertRaises(ValueError):preflight(self.output,self.binaries,'0')
        (self.output/'execution.json').write_bytes(b'claimed')
        with self.assertRaises(ValueError):preflight(self.output,self.binaries,'1')

    def test_missing_credentials_do_not_initialize_any_state(self):
        with patch.dict(os.environ,{},clear=True),patch('pilot_run.ports_available') as ports:
            with self.assertRaises(ValueError):execute(self.output,self.binaries,allowance_usd='1')
            ports.assert_not_called()
        self.assertFalse((self.output/'execution.json').exists())
        self.assertFalse((self.output/'spend').exists())

    def test_initializer_failure_records_abort_and_prevents_second_attempt(self):
        with patch.dict(os.environ,self.env,clear=True),patch('pilot_run.ports_available'),patch('pilot_run.subprocess.run',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):execute(self.output,self.binaries,allowance_usd='1')
        state=json.loads((self.output/'execution-summary.json').read_bytes())
        self.assertEqual(state['stage'],'initialization');self.assertEqual(state['status'],'attempt_aborted')
        with self.assertRaises(ValueError):preflight(self.output,self.binaries,'1')
        self.assertNotIn('test-openrouter',(self.output/'execution.json').read_text())

    def orchestration(self, fleet):
        opener=MagicMock();response=MagicMock();response.__enter__.return_value.status=200
        opener.open.return_value=response
        processes=[]
        def spawn(*args,**kwargs):
            process=Process();processes.append((process,kwargs['env']));return process
        with patch.dict(os.environ,self.env,clear=True),patch('pilot_run.ports_available'),\
             patch('pilot_run.subprocess.run') as initializers,patch('pilot_run.subprocess.Popen',side_effect=spawn),\
             patch('pilot_run.urllib.request.build_opener',return_value=opener),patch('pilot_run.run_fleet',side_effect=fleet):
            try:return execute(self.output,self.binaries,allowance_usd='1')
            finally:
                self.assertTrue(all(p.stopped for p,_ in processes))
                self.assertEqual(len(processes),2)
                self.assertNotIn('TYPESAFE_API_KEY',processes[0][1])
                self.assertNotIn('OPENROUTER_API_KEY',processes[1][1])
                self.assertTrue(all('API_KEY' not in c.kwargs['env'] for c in initializers.call_args_list))

    def test_success_records_hashes_limits_and_cleans_up(self):
        def fleet(corpus,tasks,output,**kwargs):
            self.assertEqual(kwargs['workers'],1);self.assertEqual(kwargs['scope'],'live')
            self.assertEqual(kwargs['estimate_usd'],'0.03211')
            return {'run':{'run_id':'test-run'},'summary':{'completed':2}}
        result=self.orchestration(fleet)
        self.assertFalse(result['billing_reconciled'])
        claim=json.loads((self.output/'execution.json').read_bytes())
        self.assertEqual(set(claim['binary_sha256']),set(BINARIES))
        self.assertEqual(claim['max_attempts'],2)
        self.assertEqual(json.loads((self.output/'execution-summary.json').read_bytes())['status'],'fleet_finished')

    def test_dispatch_failure_keeps_unknown_reservation(self):
        def fleet(*args,**kwargs):
            kwargs['budget'].reserve('test-attempt',request_sha256='a'*64,estimate_usd=kwargs['estimate_usd'])
            raise RuntimeError('unknown upstream result')
        with self.assertRaises(RuntimeError):self.orchestration(fleet)
        plan=json.loads((self.output/'plan.json').read_bytes())
        state=Budget(self.output/'spend',pricing_sha256=plan['files']['pricing.json']).inspect()
        self.assertEqual(state['attempts'],1)
        self.assertEqual(state['unresolved'],1)
        self.assertEqual(state['accounted_usd'],'0.03211')
        self.assertEqual(state['pending'],[{'attempt_id':'test-attempt','reserved_usd':'0.03211'}])
        self.assertEqual(json.loads((self.output/'execution-summary.json').read_bytes())['stage'],'fleet')
        with self.assertRaises(ValueError):preflight(self.output,self.binaries,'1')

    def test_changed_preflight_after_startup_prevents_fleet_dispatch(self):
        from pilot_plan import verify
        manifest=verify(self.output)
        called=[]
        def fleet(*args,**kwargs):called.append(True)
        with patch('pilot_run.verify',side_effect=[manifest,ValueError('changed evidence')]):
            with self.assertRaises(ValueError):self.orchestration(fleet)
        self.assertEqual(called,[])
        state=json.loads((self.output/'execution-summary.json').read_bytes())
        self.assertEqual(state['stage'],'startup')


if __name__=='__main__':unittest.main()
