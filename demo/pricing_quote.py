"""Offline, conservative text-pilot reservation scenarios from provider snapshots.

No network, credentials, dispatch or claims of a provider-enforced invoice cap.
"""
import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
from budget import usd_units, usd_string
from corpus import private_write

KNOWN_PRICES = {'prompt','completion','internal_reasoning','request','image','audio',
                'input_audio_cache','web_search','input_cache_read','input_cache_write','discount'}


def rate(value):
    if not isinstance(value,str) or not 1<=len(value)<=64:
        raise ValueError('price must be a bounded decimal string')
    try:number=Decimal(value)
    except InvalidOperation as error:raise ValueError('invalid token price') from error
    if not number.is_finite() or not 0<=number<=1 or 0<number<Decimal('1e-15'):
        raise ValueError('invalid token price')
    return number


def endpoint_quote(raw, *, model, provider, max_tokens):
    if len(raw)>1_048_576:raise ValueError('endpoint snapshot too large')
    data=json.loads(raw)['data']
    if data['id']!=model or 'text' not in data['architecture']['input_modalities'] or 'text' not in data['architecture']['output_modalities']:
        raise ValueError('wrong model or unsupported text modality')
    # Base slugs can match several regions/variants. This pilot requires an
    # explicit endpoint suffix, not an optimistic selection of one base price.
    if not isinstance(provider,str) or '/' not in provider:
        raise ValueError('explicit provider endpoint variant required')
    endpoints=[e for e in data['endpoints'] if e['tag']==provider]
    if len(endpoints)!=1:raise ValueError('endpoint missing or ambiguous')
    endpoint=endpoints[0]
    if endpoint['status']!=0 or 'max_tokens' not in endpoint['supported_parameters']:
        raise ValueError('endpoint unavailable or token parameter unsupported')
    context,completion=endpoint['context_length'],endpoint['max_completion_tokens']
    if any(type(n) is not int or not 1<=n<=2_000_000 for n in (context,completion)):
        raise ValueError('explicit bounded provider token capacities required')
    if type(max_tokens) is not int or not 1<=max_tokens<=min(completion,32768):
        raise ValueError('invalid requested output limit')
    prices=endpoint['pricing']
    if not isinstance(prices,dict) or set(prices)-KNOWN_PRICES or type(prices.get('discount',0)) is not int or prices.get('discount',0)!=0:
        raise ValueError('unreviewed pricing dimension')
    prompt=rate(prices['prompt']);output=rate(prices['completion'])
    reasoning=rate(prices.get('internal_reasoning','0'))
    request=rate(prices.get('request','0'))
    # Include cache read/write at the advertised full input capacity as separate
    # allowances. This intentionally over-reserves and does not assume a cache hit.
    cache_read=rate(prices.get('input_cache_read','0'))
    cache_write=rate(prices.get('input_cache_write','0'))
    with localcontext() as ctx:
        ctx.prec=80
        components={'prompt':prompt*context,'completion':output*completion,
                    'reasoning':reasoning*completion,'cache_read':cache_read*context,
                    'cache_write':cache_write*context,'request':request}
        total=sum(components.values(),Decimal(0))
    return {'model':model,'provider':provider,'requested_max_tokens':max_tokens,
            'snapshot_sha256':hashlib.sha256(raw).hexdigest(),
            'context_capacity':context,'completion_capacity':completion,
            'rates':{k:format(v,'f') for k,v in [('prompt',prompt),('completion',output),('reasoning',reasoning),('cache_read',cache_read),('cache_write',cache_write),('request',request)]},
            'components_usd':{k:format(v,'f') for k,v in components.items()},
            'capacity_scenario_usd':format(total,'f')}


def plan(directory, *, now=None):
    directory=Path(directory)
    source_raw=(directory/'sources.json').read_bytes()
    if len(source_raw)>65536:raise ValueError('source manifest too large')
    sources=json.loads(source_raw)
    now=now or datetime.now(timezone.utc)
    observed=datetime.fromisoformat(sources['observed_at'])
    if observed.tzinfo is None or not timedelta(0)<=now-observed<=timedelta(hours=24):
        raise ValueError('pricing evidence is stale or future dated')
    quotes={}
    for route,filename,model,cap in [
        ('review_standard','flash-lite.json','google/gemini-2.5-flash-lite',1024),
        ('review_deep','flash.json','google/gemini-2.5-flash',2048)]:
        raw=(directory/filename).read_bytes();source=sources['files'][filename]
        if (hashlib.sha256(raw).hexdigest()!=source['sha256'] or
                source['url']!='https://openrouter.ai/api/v1/models/'+model+'/endpoints'):
            raise ValueError('pricing source mismatch')
        quotes[route]=endpoint_quote(raw,model=model,provider='google-vertex/eu',max_tokens=cap)
    # Direct TypeSafe transport is the existing gateway implementation. Keep its
    # official documentation evidence separate from OpenRouter's Jev endpoint.
    decision=sources['decision']
    doc=(directory/'typesafe-models.html').read_bytes()
    if (decision['source_url']!='https://docs.typesafe.ai/models' or
            hashlib.sha256(doc).hexdigest()!=decision['source_sha256'] or
            decision['model']!='jev-1.13.0' or decision['max_input_tokens']!=64000 or
            decision['input_usd_per_token']!='0.000000042' or decision['output_usd_per_token']!='0'):
        raise ValueError('reviewed direct Jev price evidence required')
    with localcontext() as ctx:
        ctx.prec=80
        jev=Decimal(decision['input_usd_per_token'])*decision['max_input_tokens']
        for quote in quotes.values():
            total=(Decimal(quote['capacity_scenario_usd'])+jev)*Decimal('1.25')
            quote['reservation_usd']=usd_string(usd_units(format(total,'f')))
        maximum=max(usd_units(q['reservation_usd']) for q in quotes.values())
    return {'schema_version':1,'status':'planning_only','observed_at':sources['observed_at'],
            'expires_at':(observed+timedelta(hours=24)).isoformat(),
            'source_manifest_sha256':hashlib.sha256(source_raw).hexdigest(),
            'scope':'text and OCR transcripts only; no tools, web search, image/audio/video input',
            'basis':'full advertised input/completion capacities; separate reasoning and cache allowances; 25 percent margin',
            'decision_transport':'typesafe_direct',
            'decision':decision,'decision_capacity_scenario_usd':format(jev,'f'),
            'routes':quotes,'per_task_reservation_usd':usd_string(maximum),
            'two_task_reservation_usd':usd_string(maximum*2),
            'invoice_ceiling_guaranteed':False,'provider_calls':0,
            'unresolved':['pilot allowance not selected','provider pricing and capacities can change',
                          'account-level fees not included','no complete combined billing reconciliation',
                          'model review quality and provider contract not established for these candidates']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=plan(args.sources)
    private_write(args.output,json.dumps(result,indent=2).encode()+b'\n')
    print(json.dumps({'status':result['status'],'per_task_reservation_usd':result['per_task_reservation_usd'],
                      'two_task_reservation_usd':result['two_task_reservation_usd'],'provider_calls':0}))
