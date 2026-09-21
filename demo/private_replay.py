"""Assemble a verified replay and finding associations for the loopback viewer only."""
from pathlib import Path
from recording import canonical, verify
from review_link import link, read


def assets(corpus,tasks,run):
    run=Path(run)
    for name,maximum in [('run.json',1024*1024),('seal.json',1024*1024),('events.jsonl',32*1024*1024)]:
        read(run/'recording'/name,maximum)
    replay=verify(run/'recording')
    ids={e['task_id'] for e in replay['events']}
    if not 1<=len(ids)<=200:raise ValueError('private viewer supports 1..200 tasks')
    accepted=[e['task_id'] for e in replay['events'] if e['kind']=='task_completed' and e['data']['outcome']=='review_validated']
    links=[link(corpus,tasks,run,task_id) for task_id in accepted]
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
