"""Record one bounded gateway call without storing document text or credentials."""
import ipaddress
import json
from decimal import Decimal
import time
import urllib.error
import urllib.parse
import urllib.request
from recording import digest
from routing_trace import validate_trace


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def observe(recorder, task_id, gateway_url, text, *, timeout=15, budget=None, estimate_usd=None, on_result=None):
    url = urllib.parse.urlsplit(gateway_url)
    if (url.scheme != 'http' or not ipaddress.ip_address(url.hostname).is_loopback or
            url.username or url.password or url.query or url.fragment or url.path != '/route'):
        raise ValueError('gateway must be a literal loopback /route endpoint')
    wire = json.dumps({'request': text}).encode()
    if len(wire) > 65_536:
        raise ValueError('request too large')
    reservation = {}
    if recorder.manifest['scope'] == 'live' and budget is None:
        raise ValueError('live observation requires a shared spending ledger')
    if budget is not None:
        attempt = digest((recorder.manifest['run_id'] + ':' + task_id).encode())
        receipt = budget.reserve(attempt, request_sha256=digest(wire), estimate_usd=estimate_usd)
        reservation = {'budget_attempt_id': attempt, 'budget_reserved_usd': receipt['reserved_usd'],
                       'pricing_sha256': budget.pricing}
    recorder.append('request_started', task_id, input_sha256=digest(wire), **reservation)
    started = time.monotonic_ns()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        req = urllib.request.Request(gateway_url, data=wire, headers={'Content-Type': 'application/json'})
        try:
            response = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(1_048_577)
            status = response.status
        if len(raw) > 1_048_576:
            raise ValueError('response bound')
        body = json.loads(raw, parse_float=Decimal)
        if not isinstance(body, dict):
            raise ValueError('response object required')
        data = {'http_status': status, 'response_sha256': digest(raw),
                'elapsed_ms': (time.monotonic_ns() - started) / 1e6}
        if body.get('routing_trace') is not None:
            data['routing_trace'] = validate_trace(body['routing_trace'])
        for source, target in [('route', 'route'), ('reason', 'reason'), ('model', 'decision_model'),
                               ('policy_version', 'policy_version'), ('handler_index', 'handler_index')]:
            if body.get(source) is not None:
                data[target] = body[source]
        for key in ('input_tokens', 'output_tokens'):
            if key in body.get('usage', {}):
                data['decision_' + key] = body['usage'][key]
        execution = body.get('handler_response', {}).get('execution', {})
        for source, target in [('model', 'generation_model'), ('requested_model', 'requested_model'),
                               ('provider', 'generation_provider'), ('generation_id', 'generation_id'), ('attempt_id', 'generation_attempt_id')]:
            if execution.get(source) is not None:
                data[target] = execution[source]
        usage = execution.get('usage', {})
        for source, target in [('prompt_tokens', 'generation_input_tokens'),
                               ('completion_tokens', 'generation_output_tokens')]:
            if source in usage:
                data[target] = usage[source]
        if usage.get('cost') is not None:
            data['generation_cost_usd'] = str(usage['cost'])
        recorder.append('response_received', task_id, **data)
        # A successful transport is insufficient proof that a reviewer ran.
        if status == 200 and body.get('route') == 'fallback':
            recorder.append('task_completed', task_id, outcome='fallback')
        elif status == 200 and isinstance(body.get('handler_response'), dict) and body.get('route'):
            if on_result is not None:
                try:
                    metadata = on_result(body, raw)
                except (ValueError, TypeError, KeyError):
                    recorder.append('task_uncertain', task_id, error='review_validation_failed')
                    return
                recorder.append('review_validated', task_id, **metadata)
            recorder.append('task_completed', task_id, outcome='review_validated' if on_result else 'handler_completed')
        else:
            recorder.append('task_uncertain', task_id, error='gateway_did_not_confirm_completion')
    except (OSError, ValueError, TypeError, AttributeError):
        # No exception text: it can contain private upstream content or a prompt.
        recorder.append('task_uncertain', task_id, error='observation_failed')
