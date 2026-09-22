"""Assemble a verified replay and finding associations for the loopback viewer only."""
from pathlib import Path
from recording import canonical, verify
from review_link import link, read, parse


def load_recording(directory):
    directory=Path(directory)
    for name,maximum in [('run.json',1024*1024),('seal.json',1024*1024),('events.jsonl',32*1024*1024)]:
        read(directory/name,maximum)
    replay=verify(directory)
    ids={e['task_id'] for e in replay['events']}
    if not 1<=len(ids)<=200:raise ValueError('private viewer supports 1..200 tasks')
    return replay


def execution_assets(directory):
    replay=load_recording(directory)
    scope='synthetic provider responses' if replay['run']['scope']=='synthetic' else 'live provider responses'
    replay['presentation']={'profile':'private_execution',
        'description':f'Private execution recording with {scope}. Input receipts describe transport; model understanding and review accuracy are not established.',
        'approval':'private loopback inspection only','timing':'Measured client events; spatial paths are illustrative.'}
    return {'replay.json':(canonical(replay)+b'\n','application/json')}


def image_execution_assets(directory,reference,inspector,task_id):
    from vision_link import link
    from inspector_assets import load_bundle
    from recording import digest
    content=execution_assets(directory)
    content.update(load_bundle(inspector))
    association=link(directory,reference,inspector,task_id)
    if digest(content['evidence/manifest.json'][0])!=association['inspector_manifest_sha256']:
        raise ValueError('inspector changed during association assembly')
    replay=parse(content['replay.json'][0])
    event=next((e for e in replay['events'] if e['sha256']==association['response_event_sha256']),None)
    if replay['run']['run_id']!=association['run_id'] or event is None:
        raise ValueError('recording changed during association assembly')
    content['image-link.json']=(canonical(association)+b'\n','application/json')
    return content


def assets(corpus,tasks,run,*,inspector=None):
    run=Path(run)
    replay=load_recording(run/'recording')
    accepted=[e['task_id'] for e in replay['events'] if e['kind']=='task_completed' and e['data']['outcome']=='review_validated']
    inspector_document=parse(read(Path(inspector)/'manifest.json',1024*1024))['document_id'] if inspector else None
    links=[]
    for task_id in accepted:
        association=link(corpus,tasks,run,task_id)
        if association['document_id']==inspector_document:
            association=link(corpus,tasks,run,task_id,inspector=inspector)
        links.append(association)
    if replay['run']['scope']=='synthetic':
        description='Private recording with synthetic provider responses. Findings were checked against source spans; this does not establish review accuracy.'
    else:
        description='Private live-provider recording. Findings were checked against source spans; legal accuracy and complete billing remain separate checks.'
    replay['presentation']={'profile':'private_review','description':description,'approval':'private loopback inspection only',
                            'timing':'Measured client events; spatial paths are illustrative.'}
    body=canonical({'schema_version':1,'run_id':replay['run']['run_id'],'scope':replay['run']['scope'],
                    'publication_approved':False,'links':links})
    if len(body)>16*1024*1024:raise ValueError('private finding bundle exceeds viewer bound')
    return {'replay.json':(canonical(replay)+b'\n','application/json'),
            'review-links.json':(body+b'\n','application/json')}
