"""Derive WebVTT and SRT captions from saved ElevenLabs character alignment."""
import json,re,textwrap,sys
from pathlib import Path
if len(sys.argv)!=2: raise SystemExit('Usage: python3 demo/caption_narration.py NARRATION_DIRECTORY')
p=Path(sys.argv[1])
a=json.loads((p/'alignment.json').read_text())['alignment']
s=''.join(a['characters']);starts=a['character_start_times_seconds'];ends=a['character_end_times_seconds']
words=list(re.finditer(r'\S+',s));groups=[];group=[]
for w in words:
 if group and (w.end()-group[0].start()>76 or starts[w.start()]-starts[group[0].start()]>4.8):groups.append(group);group=[]
 group.append(w)
 if w.group()[-1] in '.?!':groups.append(group);group=[]
if group:groups.append(group)
def stamp(t):
 ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'
output=['WEBVTT',''];srt=[]
for i,g in enumerate(groups):
 start=starts[g[0].start()];end=ends[g[-1].end()-1]
 assert end>start
 caption='\n'.join(textwrap.wrap(' '.join(w.group() for w in g),width=42))
 output += [f'{stamp(start)} --> {stamp(end)}',caption,'']
 srt += [str(i+1),f'{stamp(start).replace(".",",")} --> {stamp(end).replace(".",",")}',caption,'']
(p/'captions.vtt').write_text('\n'.join(output)+'\n');(p/'captions.srt').write_text('\n'.join(srt)+'\n')
print('Caption cues:',len(groups),'end:',stamp(ends[-1]))
