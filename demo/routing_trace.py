"""Validate bounded gateway-local telemetry without permitting source content."""
from decimal import Decimal
import math
import re

BOUNDARIES = ('decision_send_started_ns', 'decision_validated_ns',
              'handler_send_started_ns', 'handler_validated_ns')
SCORES = ('confidence', 'supported', 'min_confidence', 'min_probability', 'min_supported')


def validate_trace(trace):
    if not isinstance(trace, dict) or set(trace) != {*BOUNDARIES, 'finished_ns', 'decision'}:
        raise ValueError('invalid routing trace fields')
    finish = trace['finished_ns']
    if type(finish) is not int or not 0 <= finish <= 2**53-1:
        raise ValueError('invalid trace duration')
    previous = 0
    missing = False
    for key in BOUNDARIES:
        value = trace[key]
        if value is None:
            missing = True
        elif missing or type(value) is not int or not previous <= value <= finish:
            raise ValueError('invalid trace boundary order')
        else:
            previous = value
    decision = trace['decision']
    if decision is None:
        if trace['decision_validated_ns'] is not None:
            raise ValueError('validated decision evidence missing')
        return dict(trace)
    if trace['decision_validated_ns'] is None:
        raise ValueError('decision evidence without validation')
    if not isinstance(decision, dict) or set(decision) != {*SCORES, 'choice', 'probabilities', 'route', 'reason'}:
        raise ValueError('invalid decision fields')
    probabilities = decision['probabilities']
    if (not isinstance(probabilities, dict) or not 2 <= len(probabilities) <= 33 or
            'fallback' not in probabilities or
            any(not isinstance(k,str) or not re.fullmatch('[a-z][a-z0-9_-]{0,63}', k) for k in probabilities)):
        raise ValueError('invalid decision catalog')
    def score(value):
        if type(value) not in (float, int, Decimal) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('invalid decision score')
        return float(value)
    result = {key: score(decision[key]) for key in SCORES}
    distribution = {key: score(value) for key,value in probabilities.items()}
    choice = decision['choice']
    if not isinstance(choice,str) or choice not in distribution or abs(sum(distribution.values())-1) > .001:
        raise ValueError('invalid decision distribution')
    chosen = distribution[choice]
    if any(value > chosen+1e-9 for value in distribution.values()):
        raise ValueError('decision choice is not maximum')
    if choice == 'fallback': reason = 'model_fallback'
    elif result['supported'] < result['min_supported']: reason = 'unsupported'
    elif result['confidence'] < result['min_confidence'] or chosen < result['min_probability']: reason = 'uncertain'
    elif any(k != choice and abs(value-chosen) < 1e-9 for k,value in distribution.items()): reason = 'tie'
    else: reason = 'accepted'
    route = choice if reason == 'accepted' else 'fallback'
    if decision['reason'] != reason or decision['route'] != route:
        raise ValueError('decision contradicts thresholds')
    if route == 'fallback' and trace['handler_send_started_ns'] is not None:
        raise ValueError('fallback cannot dispatch a handler')
    result.update(choice=choice, probabilities=distribution, route=route, reason=reason)
    return {**trace, 'decision': result}
