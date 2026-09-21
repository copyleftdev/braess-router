import copy
from decimal import Decimal
import unittest
from routing_trace import validate_trace


def fixture():
    return {'decision_send_started_ns':1,'decision_validated_ns':3,
            'handler_send_started_ns':4,'handler_validated_ns':8,'finished_ns':9,
            'decision':{'choice':'review','probabilities':{'review':.97,'fallback':.03},
                        'confidence':.99,'supported':.99,'min_confidence':.8,'min_probability':.8,
                        'min_supported':.8,'route':'review','reason':'accepted'}}


class TraceTests(unittest.TestCase):
    def test_decimal_scores_and_partial_timeout(self):
        trace=fixture();trace['decision']['confidence']=Decimal('.99')
        self.assertEqual(validate_trace(trace)['decision']['confidence'],.99)
        trace.update(decision=None,decision_validated_ns=None,handler_send_started_ns=None,handler_validated_ns=None)
        self.assertIsNone(validate_trace(trace)['decision'])

    def test_fallback_retains_original_model_choice(self):
        trace=fixture();trace.update(handler_send_started_ns=None,handler_validated_ns=None)
        trace['decision'].update(confidence=.1,route='fallback',reason='uncertain')
        self.assertEqual(validate_trace(trace)['decision']['choice'],'review')

    def test_rejects_invented_completion_or_reversed_time(self):
        for changes in [{'decision_send_started_ns':None},{'decision_validated_ns':5},
                        {'finished_ns':7},{'handler_validated_ns':True},{'decision':None}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_trace({**fixture(),**changes})

    def test_rejects_private_fields_and_invalid_scores(self):
        for changes in [{'prompt':'private'},{'confidence':float('nan')},{'supported':True},
                        {'route':'fallback'},{'reason':'private'},{'choice':'fallback'}]:
            trace=copy.deepcopy(fixture());trace['decision'].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_trace(trace)

    def test_fallback_cannot_claim_handler_dispatch(self):
        trace=fixture();trace['decision'].update(confidence=.1,route='fallback',reason='uncertain')
        with self.assertRaises(ValueError):validate_trace(trace)


if __name__=='__main__':unittest.main()
