"""Activate a private lexicon from its verified, indexed knowledge document."""
import argparse,hashlib,json,os
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app-home',type=Path,required=True);p.add_argument('--username',required=True)
    p.add_argument('--file',type=Path,required=True);p.add_argument('--kb-id',required=True);p.add_argument('--document-id',required=True)
    a=p.parse_args();home=a.app_home.expanduser().resolve()
    if not (home/'data.db').is_file():p.error('Existing public app-home required')
    from foreign_trade.team import runtime_env
    os.environ.update(runtime_env(home,3002))
    from features import register_package_sources,register_resource_owners,register_run_capabilities,register_product_tools
    register_package_sources();register_resource_owners();register_run_capabilities();register_product_tools()
    from core.db.engine import SessionLocal
    from core.db.models import UserShadow
    from features.knowledge.models import KBSpace,KBDocument
    from core.files.storage import get_storage
    from core.foreign_trade.lexicon import compile_markdown,activate
    raw=a.file.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    bundle=compile_markdown(raw.decode('utf-8'),a.file.name)
    with SessionLocal() as db:
        account=db.query(UserShadow.user_id).filter_by(username=a.username).one_or_none()
        if account is None:p.error('Existing account not found')
        uid=account[0]
        space=db.query(KBSpace).filter_by(kb_id=a.kb_id,user_id=uid).filter(KBSpace.deleted_at.is_(None)).one_or_none()
        doc=db.query(KBDocument).filter_by(document_id=a.document_id,kb_id=a.kb_id).filter(KBDocument.deleted_at.is_(None)).one_or_none()
        if space is None or doc is None:p.error('Knowledge document not owned by this account')
        if doc.indexing_status!='completed' or doc.checksum!=digest:p.error('Indexed source/checksum does not match')
        if hashlib.sha256(get_storage().download_bytes(doc.storage_key)).hexdigest()!=digest:p.error('Stored source bytes changed')
        lex_id=activate(db,uid,bundle,a.kb_id,a.document_id)
    print(json.dumps({'ok':True,'lexicon_id':lex_id,'version':bundle['version'],'rules':len(bundle['rules']),'source_sha256':digest,'mode':'warn_only','compiler_notes':bundle['compiler_notes']},ensure_ascii=False))

if __name__=='__main__':main()
