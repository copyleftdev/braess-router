"""Bind derived OCR text to its immutable native image and verified page geometry."""
import hashlib
import json
from pathlib import Path
from corpus import MAX_DOCUMENT, SHA, DOC_ID, private_write


def checked(root, digest, suffix, maximum):
    if not isinstance(digest,str) or not SHA.fullmatch(digest):raise ValueError('invalid evidence hash')
    path=Path(root)/'objects'/(digest+suffix)
    if path.is_symlink() or path.stat().st_size>maximum:raise ValueError('invalid evidence object')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('evidence object changed')
    return raw


def inspect(root, document):
    text=checked(root,document['source_sha256'],'.txt',MAX_DOCUMENT).decode('utf-8')
    mapping=json.loads(checked(root,document['ocr_mapping_sha256'],'.ocr.json',16*1024*1024))
    checked(root,document['native_source_sha256'],'.bin',8*1024*1024)
    if (mapping['text_sha256']!=document['source_sha256'] or mapping['source_sha256']!=document['native_source_sha256'] or
            mapping['normalization']!='ocr-tsv-word-join-v1' or not isinstance(mapping['pages'],dict) or
            not 1<=len(mapping['pages'])<=32 or not isinstance(mapping['words'],list) or len(mapping['words'])>100000):
        raise ValueError('OCR evidence binding mismatch')
    if set(mapping['pages'])!={str(i) for i in range(1,len(mapping['pages'])+1)}:
        raise ValueError('invalid OCR page sequence')
    for page in mapping['pages'].values():
        if any(type(page[k]) is not int or page[k]<=0 for k in ('width','height')) or page['width']*page['height']>16_000_000:
            raise ValueError('invalid OCR page geometry')
    previous=-1
    for word in mapping['words']:
        start,end,page=word['start_character'],word['end_character'],word['page']
        if (type(start) is not int or type(end) is not int or type(page) is not int or
                not 0<=start<end<=len(text) or start!=previous+1 or str(page) not in mapping['pages']):
            raise ValueError('invalid OCR word interval')
        if previous>=0 and text[previous:start]!=' ':raise ValueError('invalid OCR separator')
        box=word['box'];geometry=mapping['pages'][str(page)]
        if (not isinstance(box,list) or len(box)!=4 or any(type(v) is not int or v<0 for v in box) or
                box[0]+box[2]>geometry['width'] or box[1]+box[3]>geometry['height']):
            raise ValueError('invalid OCR word box')
        confidence=word['confidence']
        if type(confidence) not in (int,float) or not 0<=confidence<=100:raise ValueError('invalid OCR confidence')
        previous=end
    if (mapping['words'] and previous!=len(text)) or (not mapping['words'] and text):
        raise ValueError('unmapped OCR text')
    return text,mapping


def location(root,document,start,end):
    text,mapping=inspect(root,document)
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text):
        raise ValueError('invalid OCR finding range')
    words=[w for w in mapping['words'] if w['start_character']<end and w['end_character']>start]
    if not words:raise ValueError('finding contains no OCR evidence words')
    return {'representation':'ocr_text','normalization':mapping['normalization'],
            'native_source_sha256':document['native_source_sha256'],
            'ocr_mapping_sha256':document['ocr_mapping_sha256'],
            'image_regions':[{'page':w['page'],'box':w['box'],'ocr_confidence':w['confidence'],
                              'start_character':w['start_character'],'end_character':w['end_character']} for w in words],
            'coordinate_unit':'source_page_pixels','extraction_accuracy':'not_established'}


def import_bundle(native,ocr_directory,output,*,document_id,family_id):
    native,ocr_directory,output=Path(native),Path(ocr_directory),Path(output)
    if not DOC_ID.fullmatch(document_id) or not DOC_ID.fullmatch(family_id):raise ValueError('explicit source IDs required')
    source_paths=[native,ocr_directory/'text.txt',ocr_directory/'mapping.json']
    limits=[8*1024*1024,MAX_DOCUMENT,16*1024*1024]
    if any(p.is_symlink() or p.stat().st_size>limit for p,limit in zip(source_paths,limits)):
        raise ValueError('OCR bundle bounds exceeded')
    image,text,mapping=[p.read_bytes() for p in source_paths]
    native_hash,text_hash,mapping_hash=[hashlib.sha256(b).hexdigest() for b in (image,text,mapping)]
    document={'document_id':document_id,'family_id':family_id,'source_sha256':text_hash,
              'native_source_sha256':native_hash,'ocr_mapping_sha256':mapping_hash,
              'representation':'ocr_text','modality':'image','review_input_modality':'ocr_text',
              'normalization':'ocr-tsv-word-join-v1','characters':len(text.decode('utf-8')),
              'bytes':len(text),'object':'objects/'+text_hash+'.txt','judgments':[],
              'judgment_conflicts':[]}
    output.mkdir(mode=0o700,parents=True,exist_ok=False);(output/'objects').mkdir(mode=0o700)
    for sha,suffix,raw in [(native_hash,'.bin',image),(text_hash,'.txt',text),(mapping_hash,'.ocr.json',mapping)]:
        private_write(output/'objects'/(sha+suffix),raw)
    inspect(output,document)
    manifest={'schema_version':1,'complete':True,'scope':'native image with derived OCR; no gold relevance judgments',
              'native_media_available':True,'documents':[document]}
    private_write(output/'manifest.json',json.dumps(manifest,indent=2).encode()+b'\n')
    return manifest
