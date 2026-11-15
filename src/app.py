"""ArchivIA local desktop interface."""
from __future__ import annotations
import os, threading, hashlib
import base64
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime, timezone
from nicegui import ui
from common import read_index, write_index
from library import validate_library, reconcile
from ranking import rank_scenes
from settings import load_settings, select_library, save_settings

os.chdir(Path(__file__).resolve().parent.parent)
IDX=Path('data/index.json'); INDEX_DIR=Path('data/indexes'); settings=load_settings(); state={'screen':'library','root':None,'rows':[],'query':'','selected':None,'queue':[],'reconcile_issues':[],'model_error':None,'collection_filter':None}
if settings.get('library_root'):
    try: state['root'],_=validate_library(settings['library_root']); state['screen']='dashboard'
    except ValueError as exc:
        state['error']=str(exc)
        settings['recent']=[settings['library_root'],*[p for p in settings.get('recent',[]) if p!=settings['library_root']]][:5]
        save_settings(settings)
ui.colors(primary='#171717',secondary='#737373',accent='#171717',positive='#171717',dark='#171717',info='#525252',warning='#525252',negative='#171717')
ui.add_head_html('''<style>@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');:root{--ink:#171717;--muted:#737373;--line:#e5e5e5;--paper:#fafafa;--white:#fff}body{background:var(--paper);color:var(--ink);font-family:'DM Sans',Arial,sans-serif}.q-page{background:var(--paper)}.serif,.display{font-family:'Manrope','DM Sans',sans-serif;letter-spacing:-.035em}.muted{color:var(--muted)}.rail{background:#fff;border-right:1px solid var(--line)}.panel{background:#fff;border-left:1px solid var(--line)}.card{background:#fff;border:1px solid var(--line);border-radius:16px;box-shadow:0 1px 2px #00000005}.rowhover:hover,.navitem:hover{background:#f5f5f5}.chip{border:1px solid #d4d4d4;color:#404040;background:#fafafa;padding:3px 9px;font-size:11px;border-radius:999px}.scorebar{height:3px;background:#404040;border-radius:3px}.q-field--outlined .q-field__control:before{border-color:#d4d4d4}.q-field--outlined.q-field--focused .q-field__control:after{border-color:#171717}button:focus,input:focus{outline:2px solid #525252!important}.navactive{background:#f0f0f0!important;color:#111!important;font-weight:600}.timeline-track{height:6px;background:#e5e5e5;border-radius:8px;position:relative}.timeline-mark{position:absolute;top:-4px;width:3px;height:14px;background:#171717;border-radius:3px}.thumb-placeholder{background:#ececec}.q-btn{border-radius:10px;text-transform:none;font-weight:600}.q-card{box-shadow:none}.q-separator{background:var(--line)}.navitem{border-radius:10px;color:#525252}.navitem .q-btn__content{display:flex;justify-content:flex-start;gap:10px;width:100%}.navitem .q-icon{width:20px;min-width:20px;margin:0;justify-content:center}.kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#737373;font-weight:700}</style>''')
LOGO_DATA = 'data:image/png;base64,' + base64.b64encode(Path('docs/logo.png').read_bytes()).decode('ascii')
def index_path(root=None):
    root=Path(root or state.get('root') or '').expanduser().resolve()
    digest=hashlib.sha256(str(root).encode('utf-8')).hexdigest()
    return INDEX_DIR/f'{digest}.json'
def idx():
    path=index_path()
    try:
        data=read_index(path)
        if path.exists():state.pop('index_error',None);return data
        # Preserve the former shared index while copying only this archive's entries.
        legacy=read_index(IDX)
        root=Path(state['root']).resolve()
        videos=[]
        for video in legacy.get('videos',[]):
            try:Path(video.get('path','')).resolve().relative_to(root)
            except (ValueError,OSError):continue
            videos.append(video)
        data['videos']=videos
        write_index(path,data)
        state.pop('index_error',None)
        return data
    except Exception as e:state['index_error']=str(e);return {'schema_version':1,'videos':[]}
def save_idx(data, root=None):write_index(index_path(root),data)
def rel(path):
    try:return str(Path(path).resolve().relative_to(state['root']))
    except:return Path(path).name
def thumb(scene):
    key=Path(scene.get('keyframe',''))
    target=Path(scene.get('thumbnail') or key.with_name(key.stem+'_thumb.jpg'))
    if target.is_file():return target
    if key.is_file():
        try:
            import cv2
            image=cv2.imread(str(key))
            if image is not None:
                h,w=image.shape[:2];scale=320/max(w,h);target.parent.mkdir(parents=True,exist_ok=True)
                cv2.imwrite(str(target),cv2.resize(image,(max(1,int(w*scale)),max(1,int(h*scale)))))
                if target.is_file():return target
        except Exception:pass
    return None
def refresh_results(*, refresh_ui=True):
    data=idx()
    try:
        state['rows']=rank_scenes(data,state['query']) if state['query'].strip() else [{'scene':s,'score':0,'visual_similarity':0,'keyword_overlap':0} for v in data['videos'] for s in v.get('scenes',[])]
        state['model_error']=None
    except Exception:state['model_error']='modèle indisponible — recherche visuelle hors service';state['rows']=[{'scene':s,'score':0,'visual_similarity':0,'keyword_overlap':0} for v in data['videos'] for s in v.get('scenes',[])]
    state['selected']=None
    if refresh_ui:
        render.refresh()
def path_dialog():
    start = Path(state.get('root') or settings.get('library_root') or Path.home()).expanduser()
    if not start.is_dir(): start=Path.home()
    browser={'path':start.resolve()}
    with ui.dialog() as d,ui.card().classes('card w-[min(760px,95vw)] max-h-[85vh]'):
        ui.label('Ouvrir un dossier d’archives').classes('serif text-2xl')
        ui.label('Parcourez les dossiers, puis choisissez celui qui contient vos vidéos.').classes('muted text-sm')
        p=ui.input('Chemin du dossier',value=str(browser['path'])).props('outlined').classes('w-full')
        breadcrumb=ui.row().classes('w-full items-center gap-1 flex-wrap')
        listing=ui.column().classes('w-full gap-1 overflow-y-auto max-h-[42vh]')
        def select_folder(path=None):
            chosen=Path(path or p.value).expanduser()
            try:
                root,files=validate_library(chosen);global settings;settings=select_library(settings,root);state.update(root=root,screen='dashboard')
                if not files:ui.notify('Aucune vidéo prise en charge dans ce dossier.',type='warning')
                d.close();refresh_results();refresh_library(quiet=True)
            except Exception as e:ui.notify(str(e),type='negative')
        def browse(path):
            candidate=Path(path).expanduser()
            try:
                candidate=candidate.resolve(strict=True)
                if not candidate.is_dir() or not os.access(candidate,os.R_OK|os.X_OK): raise ValueError('Dossier inaccessible en lecture.')
                browser['path']=candidate;p.value=str(candidate)
                breadcrumb.clear()
                with breadcrumb:
                    ui.button('⌂',on_click=lambda: browse(Path.home())).props('flat dense').tooltip('Accueil')
                    parts=[candidate.anchor]
                    current=Path(candidate.anchor)
                    for part in candidate.parts[1:]:
                        current=current/part;parts.append((part,current))
                    for entry in parts[1:]:
                        name,target=entry
                        ui.label('/').classes('muted')
                        ui.button(name,on_click=lambda target=target:browse(target)).props('flat dense')
                listing.clear()
                with listing:
                    if candidate.parent!=candidate:
                        ui.button('↑  Dossier parent',on_click=lambda:browse(candidate.parent)).props('flat').classes('w-full justify-start')
                    try: dirs=sorted((x for x in candidate.iterdir() if x.is_dir() and not x.is_symlink() and not x.name.startswith('.')),key=lambda x:x.name.casefold())
                    except OSError as e: dirs=[];ui.label(f'Impossible de lire ce dossier : {e}').classes('text-neutral-700')
                    if not dirs: ui.label('Aucun sous-dossier. Vous pouvez choisir ce dossier ou coller un autre chemin.').classes('muted text-sm p-3')
                    for folder in dirs:
                        ui.button('📁  '+folder.name,on_click=lambda folder=folder:browse(folder)).props('flat').classes('w-full justify-start')
            except Exception as e:ui.notify(str(e),type='negative')
        p.on('keydown.enter',lambda: browse(p.value))
        browse(browser['path'])
        with ui.row().classes('justify-between w-full items-center'):
            ui.label('Les vidéos restent dans leur emplacement.').classes('muted text-xs')
            with ui.row():
                ui.button('Annuler',on_click=d.close).props('flat')
                ui.button('Choisir ce dossier',on_click=lambda:select_folder(browser['path'])).props('outline')
                ui.button('Ouvrir le chemin',on_click=lambda:select_folder()).props('color=primary')
    d.open()
def recent_dialog():
    with ui.dialog() as d,ui.card().classes('card w-[560px]'):
        ui.label('Dossiers récents').classes('serif text-xl')
        for item in settings.get('recent',[]):
            with ui.row().classes('w-full items-center'):
                ui.label(item).classes('muted text-xs flex-1 break-all')
                def choose(item=item):
                    try:
                        root,_=validate_library(item)
                        global settings
                        settings=select_library(settings,root)
                        state.update(root=root,screen='dashboard')
                        d.close();refresh_results();refresh_library(quiet=True)
                    except Exception as e:ui.notify(str(e),type='negative')
                ui.button('Choisir',on_click=choose).props('flat');ui.button('×',on_click=lambda item=item:remove_recent(item)).props('flat')
        ui.button('Fermer',on_click=d.close).props('flat')
    d.open()
def remove_recent(item):settings['recent']=[x for x in settings['recent'] if x!=item];save_settings(settings);render.refresh()
def about():
    with ui.dialog() as d,ui.card().classes('card max-w-[620px]'):
        ui.label('À propos et limites').classes('serif text-2xl');ui.label('ArchivIA propose des scènes à examiner. Les scores et transcriptions peuvent être erronés. La machine ne valide jamais, ne reconnaît pas les personnes et ne modifie pas les vidéos. Les droits sont déclaratifs, jamais vérifiés automatiquement.').classes('muted whitespace-normal');ui.button('Fermer',on_click=d.close).props('flat')
    d.open()
def library_screen():
    with ui.column().classes('w-full min-h-screen items-center justify-center p-8'):
        ui.image(LOGO_DATA).classes('w-52 h-40 object-contain')
        ui.label('La mémoire audiovisuelle, retrouvée.').classes('display text-3xl text-center mt-4')
        ui.label('Un espace de travail local pour explorer, rechercher et documenter vos archives.').classes('muted text-center max-w-xl')
        with ui.card().classes('card w-full max-w-2xl mt-8 p-6'):
            ui.label('Commencer avec une collection').classes('font-semibold text-lg')
            ui.label('Choisissez le dossier qui contient vos vidéos. Elles restent à leur emplacement d’origine.').classes('muted text-sm mb-4')
            with ui.row().classes('w-full items-center justify-between'):
                ui.button('Ouvrir un dossier',on_click=path_dialog,icon='folder_open').props('color=primary')
                ui.button('Dossiers récents',on_click=recent_dialog).props('flat')
            if state.get('error'):ui.label('Dossier précédent inaccessible : '+state['error']).classes('text-sm mt-3')
        ui.button('À propos et limites',on_click=about).props('flat').classes('mt-4')
def rights_dialog(item):
    with ui.dialog() as dialog,ui.card().classes('card w-[min(560px,95vw)]'):
        ui.label('Déclarer les droits · '+item['path'].name).classes('serif text-xl')
        fields={k:ui.input(label).props('outlined').classes('w-full') for k,label in [('holder','Titulaire'),('license','Licence ou statut'),('allowed_uses','Usages autorisés')]}
        apply_all=ui.checkbox('Appliquer à toute la file')
        def launch(unknown=False):
            rights={} if unknown else {key:field.value for key,field in fields.items()}
            if not unknown and not all(rights.values()):
                ui.notify('Renseignez les trois champs ou choisissez sans droits déclarés.',type='warning')
                return
            targets=[queued for queued in state['queue'] if queued['stage']=='Droits requis'] if apply_all.value else [item]
            for target in targets:target.update(stage='En attente',error=None)
            dialog.close()
            if len(targets)>1:ingest_batch(targets,rights)
            else:ingest(targets[0]['path'],rights,targets[0])
            render.refresh()
        with ui.row().classes('w-full justify-end'):
            ui.button('Annuler',on_click=dialog.close).props('flat')
            ui.button('Indexer sans droits déclarés',on_click=lambda:launch(True)).props('flat')
            ui.button('Enregistrer et indexer',on_click=lambda:launch()).props('color=primary')
    dialog.open()

PROGRESS_BY_STAGE={'En attente':0,'Détection des scènes':10,'Transcription':30,'Images clés':55,'Représentations visuelles':75,'Enregistrement':90,'Terminé':100}
def update_ingest_progress(entry,stage):
    entry['stage']=stage

def sync_ingest_progress():
    """Poll the ingest queue and drive the progress widgets.

    This timer lives on the page (not on a dialog), so it survives the
    ``render.refresh()`` calls that rebuild the queue card and the widget
    references stored on each entry.
    """
    recompose=False
    for entry in state['queue']:
        stage=entry.get('stage','En attente')
        widgets=entry.get('_progress_ui')
        if widgets and widgets['bar'].is_deleted:
            entry.pop('_progress_ui',None)
        elif widgets:
            percent=PROGRESS_BY_STAGE.get(stage,0)
            widgets['stage'].text=f"{entry['path'].name} · {stage}"
            widgets['bar'].value=percent/100
            widgets['percent'].text=f'{percent}%'
        if stage in ('Terminé','Échec') and not entry.get('_progress_reported'):
            entry['_progress_reported']=True
            recompose=True
    if recompose:
        # The worker has persisted the index before reaching Terminé.
        # Refresh once at completion so the new video appears.
        render.refresh()
    active=[entry for entry in state['queue'] if entry.get('stage')!='Droits requis']
    if active and all(entry.get('stage') in ('Terminé','Échec') for entry in active):
        # All ingestion work reached 100%: reconcile the library immediately
        # so the freshly indexed videos show up and the finished queue clears.
        # Reconcile replaces the queue, so this runs only once per batch.
        try:
            refresh_library(quiet=True)
        except Exception:
            render.refresh()

def ingest(path,rights,entry=None):
    if entry is None:
        entry={'path':path,'stage':'En attente','error':None};state['queue'].append(entry)
    library_root=Path(state['root']).resolve()
    def worker():
        from ingest import ingest_video
        try:
            records=ingest_video(path,rights,frames_dir=Path('data/frames'),library_root=library_root,progress=lambda stage:update_ingest_progress(entry,stage));update_ingest_progress(entry,'Enregistrement');data=read_index(index_path(library_root));st=path.stat()
            data['videos']=[v for v in data['videos'] if str(Path(v.get('path','')).resolve())!=str(path.resolve())]
            for s in records:s['rights_declared']=bool(rights)
            data['videos'].append({'path':str(path.resolve()),'relative_path':str(path.relative_to(library_root)),'size':st.st_size,'mtime':st.st_mtime,'rights':rights,'missing':False,'models':{'transcription':'openai/whisper-base','visual_embedding':'open_clip/ViT-B-32:laion2b_s34b_b79k'},'scenes':records});save_idx(data,library_root);entry['stage']='Terminé'
        except Exception as e:entry.update(stage='Échec',error=str(e))
    threading.Thread(target=worker,daemon=True).start()

def ingest_batch(entries,rights):
    library_root=Path(state['root']).resolve()
    def worker():
        from ingest import ingest_video
        for entry in entries:
            path=entry['path']
            try:
                records=ingest_video(path,rights,frames_dir=Path('data/frames'),library_root=library_root,progress=lambda stage,entry=entry:update_ingest_progress(entry,stage));update_ingest_progress(entry,'Enregistrement')
                data=read_index(index_path(library_root));st=path.stat()
                data['videos']=[v for v in data['videos'] if str(Path(v.get('path','')).resolve())!=str(path.resolve())]
                for scene in records:scene['rights_declared']=bool(rights)
                data['videos'].append({'path':str(path.resolve()),'relative_path':str(path.relative_to(library_root)),'size':st.st_size,'mtime':st.st_mtime,'rights':rights,'missing':False,'models':{'transcription':'openai/whisper-base','visual_embedding':'open_clip/ViT-B-32:laion2b_s34b_b79k'},'scenes':records})
                save_idx(data,library_root);entry['stage']='Terminé'
            except Exception as exc:entry.update(stage='Échec',error=str(exc))
    threading.Thread(target=worker,daemon=True).start()
def refresh_library(*,quiet=False):
    if state.get('index_error'):
        ui.notify('Index illisible : actualisation désactivée pour préserver le fichier.',type='negative')
        return
    data=idx();queue,missing=reconcile(state['root'],data)
    if missing:save_idx(data)
    indexed={str(Path(v.get('path','')).resolve()):v for v in data.get('videos',[]) if v.get('path')}
    issues=[{'video':video,'reason':'missing'} for video in missing]
    for path,reason in queue:
        if reason=='modifié':
            video=indexed.get(str(path.resolve()))
            if video:
                issues.append({'video':video,'reason':'changed'})
    state['reconcile_issues']=issues
    state['queue']=[{'path':p,'reason':reason,'stage':'Droits requis','error':None} for p,reason in queue]
    if not queue and not quiet:ui.notify('Index à jour : aucune nouvelle vidéo.')
    render.refresh()

def unindex_video(video_path):
    if state.get('index_error'):
        ui.notify('Index illisible : désindexation désactivée.',type='negative')
        return
    target=str(Path(video_path).resolve())
    data=idx()
    before=len(data.get('videos',[]))
    removed=[video for video in data.get('videos',[])
             if str(Path(video.get('path','')).resolve())==target]
    data['videos']=[video for video in data.get('videos',[])
                    if str(Path(video.get('path','')).resolve())!=target]
    if len(data['videos'])==before:
        ui.notify('Cette vidéo n’est plus présente dans l’index.',type='warning')
    else:
        save_idx(data)
        frames_root=Path('data/frames').resolve()
        cleanup_errors=[]
        for video in removed:
            for scene in video.get('scenes',[]):
                for field in ('keyframe','thumbnail'):
                    generated=Path(scene.get(field,'')).resolve()
                    try:
                        generated.relative_to(frames_root)
                    except ValueError:
                        continue
                    try:
                        generated.unlink(missing_ok=True)
                    except OSError as exc:
                        cleanup_errors.append(str(exc))
        state['rows']=[row for row in state['rows']
                       if str(Path(row['scene'].get('video_path','')).resolve())!=target]
        state['selected']=None
        if cleanup_errors:
            ui.notify('Vidéo retirée de l’index, mais certaines images clés n’ont pas pu être supprimées.',type='warning')
        else:
            ui.notify('Vidéo, scènes et images clés générées retirées.')
    refresh_library()

def confirm_unindex_video(video):
    video_path=video.get('path','')
    with ui.dialog() as dialog,ui.card().classes('card w-[min(520px,95vw)]'):
        ui.label('Désindexer cette vidéo ?').classes('serif text-xl')
        ui.label(f"{Path(video_path).name} sera retirée de l’index avec ses scènes et ses images clés générées. Le fichier vidéo original restera à sa place.").classes('muted text-sm whitespace-normal')
        with ui.row().classes('w-full justify-end'):
            ui.button('Annuler',on_click=dialog.close).props('flat')
            ui.button('Désindexer',on_click=lambda:(dialog.close(),unindex_video(video_path))).props('color=negative')
    dialog.open()
def set_status(scene,status):
    if state.get('index_error'):
        ui.notify('Index illisible : décisions désactivées.',type='negative')
        return
    data=idx();match=None
    for v in data['videos']:
        for s in v.get('scenes',[]):
            if s.get('scene_id')==scene.get('scene_id') and s.get('video_path')==scene.get('video_path'):match=s;break
    if match is None:return
    old={k:match.get(k) for k in ('status','reviewed_by','reviewed_at')};match.update(status=status,reviewed_by='archiviste',reviewed_at=datetime.now(timezone.utc).isoformat());scene['status']=status;save_idx(data)
    def undo():
        data=idx()
        for v in data['videos']:
            for s in v.get('scenes',[]):
                if s.get('scene_id')==scene.get('scene_id') and s.get('video_path')==scene.get('video_path'):
                    for k,val in old.items():s.pop(k,None) if val is None else s.update({k:val})
        scene['status']=old.get('status') or 'proposé';save_idx(data);ui.notify('Décision annulée');render.refresh()
    state['undo']=undo
    ui.timer(5,expire_undo,once=True)
    ui.notify(f'{status}. L’annulation reste disponible dans le panneau pendant 5 s.',timeout=5000);render.refresh()
def undo_last():
    action=state.pop('undo',None)
    if action:action()
def expire_undo():
    state.pop('undo',None)
    render.refresh()
def do_search(q):state.update(query=q or '',selected=None,screen='search');refresh_results()
def choose_scene(scene):state.update(selected=scene,screen='search');render.refresh()
def navigate(screen):state['screen']=screen;render.refresh()
def change_screen():navigate('dashboard')
def video_group(video):
    relative=Path(video.get('relative_path') or video.get('path',''))
    parent=relative.parent.as_posix()
    return parent if parent not in ('','.','/') else 'Racine'
def all_videos():return idx().get('videos',[])
def all_scenes():return [s for v in all_videos() for s in v.get('scenes',[])]
def scene_video(scene):
    return next((v for v in all_videos() if str(Path(v.get('path','')).resolve())==str(Path(scene.get('video_path','')).resolve())),{})
def video_thumb(video):
    """Return the first available scene thumbnail for a video."""
    for scene in video.get('scenes',[]):
        pic=thumb(scene)
        if pic:return pic
    return None
def title_matches(video,query):
    """Match a title exactly, by substring, or approximately to tolerate typos."""
    query=' '.join(query.casefold().split())
    if not query:return True
    title=Path(video.get('path','')).name.casefold()
    if query in title:return True
    ratio=SequenceMatcher(None,query,title).ratio()
    # Compare against title windows too, so a short query can match inside a long filename.
    words=title.replace('_',' ').replace('-',' ').split()
    candidates=words+[title]
    for word in words:
        if len(word)>=len(query):
            candidates.extend(word[i:i+len(query)] for i in range(len(word)-len(query)+1))
    ratio=max([ratio,*[SequenceMatcher(None,query,candidate).ratio() for candidate in candidates]])
    return ratio>=0.62
def filtered_rows():
    rows=state['rows'];group=state.get('collection_filter')
    if group:rows=[r for r in rows if video_group(scene_video(r['scene']))==group]
    return rows
def scene_card(scene,compact=False,result=None):
    pic=thumb(scene)
    with ui.row().classes('rowhover w-full items-center gap-4 p-3 rounded-xl cursor-pointer').on('click',lambda scene=scene:choose_scene(scene)):
        if pic:ui.image(str(pic)).classes('w-28 h-16 object-cover rounded-lg shrink-0')
        else:ui.element('div').classes('thumb-placeholder w-28 h-16 rounded-lg shrink-0')
        with ui.column().classes('flex-1 min-w-0 gap-1'):
            ui.label(Path(scene.get('video_path','Archive')).name).classes('font-semibold truncate')
            ui.label(f"{rel(scene.get('video_path',''))}  ·  {scene.get('start','00:00:00')} – {scene.get('end','00:00:00')}").classes('muted text-xs truncate')
            if not compact:ui.label(scene.get('transcript') or 'Aucune parole transcrite').classes('muted text-sm line-clamp-2')
            if result is not None:
                ui.label(f"Visuel {result.get('visual_similarity', 0):.3f}  ·  Mots-clés {result.get('keyword_overlap', 0):.3f}").classes('muted text-xs')
        if result is not None:
            with ui.column().classes('items-end gap-1 shrink-0'):
                ui.label(f"{result.get('score', 0):.3f}").classes('font-bold text-base')
                ui.label('Score indicatif').classes('muted text-xs')
        status=scene.get('status','proposé')
        ui.label('À examiner' if status=='proposé' else status.title()).classes('chip')
def sidebar():
    with ui.column().classes('rail w-[248px] shrink-0 h-screen p-5'):
        ui.image(LOGO_DATA).classes('w-36 h-[108px] object-contain self-start mb-2')
        ui.label('ESPACE DE TRAVAIL').classes('kicker px-3 mt-2 mb-2')
        for screen,label,icon in [('dashboard','Vue d’ensemble','space_dashboard'),('search','Recherche de scènes','search'),('collections','Collections','video_library'),('review','Validation humaine','fact_check')]:
            active=state['screen']==screen
            with ui.button(on_click=lambda screen=screen:navigate(screen),icon=icon).props('flat no-caps').classes(f'navitem w-full justify-start px-3 py-2 {"navactive" if active else ""}'):
                ui.label(label)
        ui.space()
        root_label=str(state.get('root') or 'Aucune archive')
        with ui.card().classes('card w-full p-3 mb-3'):
            ui.label('COLLECTION ACTIVE').classes('kicker')
            ui.label(Path(root_label).name or root_label).classes('font-semibold truncate w-full mt-1')
            ui.label(root_label).classes('muted text-xs truncate w-full')
        ui.button('Changer d’archive',on_click=path_dialog,icon='folder_open').props('flat no-caps').classes('w-full justify-start')
        ui.button('À propos et limites',on_click=about,icon='info').props('flat no-caps').classes('w-full justify-start')
def page_header(title,subtitle,action=None):
    with ui.row().classes('w-full justify-between items-start mb-2'):
        with ui.column().classes('gap-1'):
            ui.label(title).classes('display text-3xl font-bold')
            ui.label(subtitle).classes('muted text-sm')
        if action:action()
def dashboard_screen():
    videos=all_videos();scenes=all_scenes();pending=[s for s in scenes if s.get('status','proposé')=='proposé']
    with ui.column().classes('w-full min-w-0 p-8 gap-6'):
        page_header('Vue d’ensemble','Votre espace de repérage audiovisuel.',lambda:ui.button('Actualiser la bibliothèque',on_click=refresh_library,icon='sync').props('outline'))
        if state.get('queue'):
            with ui.card().classes('card w-full p-4'):
                ui.label('Nouveaux fichiers à indexer').classes('font-semibold')
                for item in state['queue']:
                    with ui.row().classes('w-full items-center'):
                        detail=' · fichier modifié' if item.get('reason')=='modifié' else ''
                        stage_label=ui.label(f"{item['path'].name}{detail} · {item['stage']}").classes('flex-1')
                        if item['stage']=='Droits requis':
                            ui.button('Déclarer les droits',on_click=lambda item=item:rights_dialog(item)).props('flat')
                        elif item.get('error'):
                            ui.label(str(item['error'])).classes('muted text-xs')
                        if item['stage'] in PROGRESS_BY_STAGE:
                            percent=PROGRESS_BY_STAGE[item['stage']]
                            progress_bar=ui.linear_progress(value=percent/100).props('rounded').classes('w-32')
                            progress_label=ui.label(f'{percent}%').classes('muted text-xs w-10 text-right')
                            item['_progress_ui']={'stage':stage_label,'bar':progress_bar,'percent':progress_label}
        if state.get('reconcile_issues'):
            with ui.card().classes('card w-full p-4'):
                ui.label('Vidéos indexées à vérifier').classes('font-semibold')
                for issue in state['reconcile_issues']:
                    video=issue['video'];path=video.get('path','');changed=issue['reason']=='changed'
                    description='Fichier modifié depuis l’indexation' if changed else 'Fichier introuvable dans la collection'
                    with ui.row().classes('w-full items-center'):
                        ui.label(f"{Path(path).name} · {description}").classes('flex-1')
                        ui.button('Désindexer',on_click=lambda video=video:confirm_unindex_video(video)).props('flat color=negative')
        with ui.row().classes('w-full gap-4'):
            for label,value,caption,icon in [('Vidéos',len(videos),'dans cette archive','movie'),('Scènes indexées',len(scenes),'repères disponibles','view_timeline'),('À examiner',len(pending),'validation humaine','fact_check')]:
                with ui.card().classes('card flex-1 min-w-[170px] p-5'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label(label).classes('muted text-sm');ui.icon(icon).classes('text-xl text-neutral-600')
                    ui.label(str(value)).classes('display text-3xl font-bold mt-2');ui.label(caption).classes('muted text-xs')
        with ui.card().classes('card w-full p-5'):
            ui.label('Chercher dans vos archives').classes('display text-xl font-bold')
            ui.label('Décrivez une image, un geste ou un moment. Les suggestions restent à valider.').classes('muted text-sm mt-1 mb-4')
            with ui.row().classes('w-full items-center'):
                q=ui.input(placeholder='Ex. une foule qui traverse une place sous la pluie').props('outlined').classes('flex-1')
                q.on('keydown.enter',lambda:do_search(q.value))
                ui.button('Rechercher',on_click=lambda:do_search(q.value),icon='search').props('color=primary').classes('ml-2')
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Collections').classes('display text-xl font-bold')
            ui.button('Parcourir toutes',on_click=lambda:navigate('collections')).props('flat')
        if videos:
            with ui.column().classes('w-full gap-2'):
                for video in videos:
                    video_path=video.get('path','')
                    relative=video.get('relative_path') or video_path
                    pic=video_thumb(video)
                    with ui.card().classes('card w-full p-3'):
                        with ui.row().classes('w-full items-center gap-4'):
                            if pic:ui.image(str(pic)).classes('w-32 h-[72px] object-cover rounded-lg shrink-0')
                            else:ui.element('div').classes('thumb-placeholder w-32 h-[72px] rounded-lg shrink-0 flex items-center justify-center').props('aria-label="Aucune vignette disponible"')
                            with ui.column().classes('flex-1 min-w-0 gap-1'):
                                ui.label(Path(video_path).name or 'Vidéo').classes('font-semibold truncate')
                                ui.label(relative).classes('muted text-sm truncate')
                            ui.label(f"{len(video.get('scenes',[]))} scènes").classes('muted text-xs shrink-0')
        else:
            with ui.card().classes('card w-full p-8 items-center'):
                ui.icon('video_library').classes('text-3xl text-neutral-500');ui.label('Aucune vidéo indexée pour le moment').classes('font-semibold mt-2');ui.label('Actualisez la bibliothèque pour découvrir les vidéos de ce dossier.').classes('muted text-sm')
                ui.button('Actualiser la bibliothèque',on_click=refresh_library).props('outline').classes('mt-3')
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('À examiner').classes('display text-xl font-bold')
            ui.button('Ouvrir la file',on_click=lambda:navigate('review')).props('flat')
        if pending:
            with ui.card().classes('card w-full p-2'):
                for scene in pending[:4]:scene_card(scene,compact=True)
        else:ui.label('La file de validation est vide.').classes('muted text-sm')
def collection_card(name,items):
    first=next((s for v in items for s in v.get('scenes',[])),None);pic=thumb(first) if first else None
    with ui.card().classes('card w-[min(260px,100%)] flex-1 cursor-pointer overflow-hidden').on('click',lambda name=name:open_collection(name)):
        if pic:ui.image(str(pic)).classes('w-full h-32 object-cover')
        else:ui.element('div').classes('thumb-placeholder w-full h-32')
        with ui.column().classes('p-4 gap-1'):
            ui.label(name).classes('font-semibold');ui.label(f"{len(items)} vidéos · {sum(len(v.get('scenes',[])) for v in items)} scènes").classes('muted text-xs')
def open_collection(name):
    state['collection_filter']=name;state['query']='';state['screen']='search';refresh_results()
def collections_screen():
    videos=all_videos()
    with ui.column().classes('w-full min-w-0 p-8 gap-6'):
        page_header('Collections','Toutes les vidéos indexées dans votre archive.',lambda:ui.button('Actualiser',on_click=refresh_library,icon='sync').props('outline'))
        if not videos:ui.label('Aucune vidéo indexée. Actualisez la bibliothèque ou choisissez un dossier.').classes('muted')
        else:
            search=ui.input(placeholder='Rechercher une vidéo par titre…').props('outlined clearable').classes('w-full')
            filtered={'videos':videos}
            count_label=ui.label(f'{len(videos)} vidéos').classes('muted text-sm')
            listing=ui.column().classes('w-full gap-2')
            def show_videos():
                filtered['videos']=[video for video in videos if title_matches(video,search.value or '')]
                count_label.text=f"{len(filtered['videos'])} vidéo"+('' if len(filtered['videos'])==1 else 's')
                listing.clear()
                with listing:
                    if not filtered['videos']:
                        ui.label('Aucune vidéo ne correspond à ce titre.').classes('muted p-4')
                    for video in filtered['videos']:
                        render_collection_video(video)
            search.on_value_change(lambda _:show_videos())
            show_videos()
def render_collection_video(video):
    video_path=video.get('path','')
    relative=video.get('relative_path') or video_path
    missing=video.get('missing',False) or not Path(video_path).is_file()
    pic=video_thumb(video)
    with ui.card().classes('card w-full p-4'):
        with ui.row().classes('w-full items-center gap-4'):
            if pic:ui.image(str(pic)).classes('w-32 h-[72px] object-cover rounded-lg shrink-0')
            else:ui.element('div').classes('thumb-placeholder w-32 h-[72px] rounded-lg shrink-0')
            with ui.column().classes('flex-1 min-w-0 gap-1'):
                ui.label(Path(video_path).name or 'Vidéo').classes('font-semibold truncate')
                ui.label(relative).classes('muted text-xs break-all')
                label=f"{len(video.get('scenes',[]))} scènes"
                if missing:label+=' · fichier manquant'
                ui.label(label).classes('muted text-xs')
            ui.button('Désindexer',on_click=lambda video=video:confirm_unindex_video(video)).props('outline color=negative')
def search_screen():
    data=idx();rows=filtered_rows()
    with ui.column().classes('w-full min-w-0 p-8 gap-5'):
        page_header('Recherche de scènes','Décrivez ce que vous cherchez dans vos archives.',lambda:ui.button('Toutes les scènes',on_click=lambda:clear_collection()).props('flat'))
        if state.get('collection_filter'):ui.label(f"Collection : {state['collection_filter']}").classes('chip self-start')
        if state.get('index_error'):ui.label('Index illisible — affichage en lecture seule : '+state['index_error']).classes('muted')
        if state.get('model_error'):ui.label(state['model_error']).classes('muted border p-3 rounded-xl')
        with ui.card().classes('card w-full p-4'):
            with ui.row().classes('w-full items-center'):
                q=ui.input(placeholder='Décrivez une scène, un lieu ou une action…',value=state['query']).props('outlined').classes('flex-1')
                q.on('keydown.enter',lambda:do_search(q.value))
                ui.button('Rechercher',on_click=lambda:do_search(q.value),icon='search').props('color=primary').classes('ml-2')
            ui.label('Recherche visuelle et transcription · les scores classent des suggestions, ils ne mesurent pas une certitude.').classes('muted text-xs mt-2')
        if state.get('undo'):ui.button('Annuler la dernière décision',on_click=undo_last).props('flat')
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(f"{len(rows)} scènes · {len(data['videos'])} vidéos").classes('muted text-sm')
            ui.button('Actualiser',on_click=refresh_library,icon='sync').props('flat')
        with ui.row().classes('w-full items-start gap-5 no-wrap'):
            with ui.column().classes('flex-1 min-w-0 gap-2'):
                if not data['videos']:ui.label('Aucune vidéo indexée. Actualisez la bibliothèque pour commencer.').classes('muted p-4')
                elif not rows:ui.label('Aucun résultat pour cette recherche.').classes('muted p-4')
                for result in rows:scene_card(result['scene'],result=result)
            with ui.column().classes('panel card w-[min(36vw,440px)] min-w-[320px] p-5 gap-3'):inspector()
def clear_collection():
    state.update(collection_filter=None,query='');refresh_results()
def inspector():
    scene=state.get('selected')
    if not scene:
        ui.icon('movie_edit').classes('text-2xl text-neutral-500');ui.label('Inspection de scène').classes('display text-xl font-bold')
        ui.label('Sélectionnez une vignette pour examiner son contexte et prendre une décision.').classes('muted text-sm');return
    pic=thumb(scene)
    if pic:ui.image(str(pic)).classes('w-full aspect-video object-cover rounded-xl bg-neutral-100')
    else:ui.element('div').classes('thumb-placeholder w-full aspect-video rounded-xl')
    video=scene_video(scene);rights=video.get('rights',{})
    ui.label(Path(scene.get('video_path','Archive')).name).classes('display text-xl font-bold mt-2')
    ui.label(rel(scene.get('video_path',''))).classes('muted text-xs break-all')
    ui.label(scene.get('transcript') or 'Aucune parole transcrite pour cette scène.').classes('text-sm whitespace-normal mt-2')
    siblings=sorted(video.get('scenes',[]),key=lambda s:s.get('start_seconds',0));duration=max([s.get('end_seconds',0) for s in siblings] or [1]) or 1
    ui.label('LIGNE DU TEMPS').classes('kicker mt-3')
    track=ui.element('div').classes('timeline-track w-full mt-2')
    with track:
        for item in siblings:
            left=max(0,min(100,item.get('start_seconds',0)/duration*100));ui.element('div').classes('timeline-mark').style(f'left:{left:.2f}%')
    with ui.row().classes('w-full flex-wrap gap-1'):
        for item in siblings:ui.button(item.get('start','00:00'),on_click=lambda item=item:choose_scene(item)).props('flat dense').classes('text-xs')
    ui.label(f"{scene.get('start','00:00:00')} – {scene.get('end','00:00:00')}  ·  {int(scene.get('end_seconds',0)-scene.get('start_seconds',0))} s").classes('muted text-xs')
    ui.separator();ui.label('Droits déclarés').classes('font-semibold text-sm')
    ui.label(f"{rights.get('holder','Non déclaré')} · {rights.get('license','Statut non déclaré')} · {rights.get('allowed_uses','Usages inconnus')}").classes('muted text-xs whitespace-normal')
    ui.label(f"Statut : {scene.get('status','proposé')}").classes('chip self-start mt-1')
    with ui.row().classes('w-full mt-2'):
        ui.button('Valider',on_click=lambda:set_status(scene,'validé'),icon='check').props('color=primary').classes('flex-1')
        ui.button('Rejeter',on_click=lambda:set_status(scene,'rejeté'),icon='close').props('outline').classes('flex-1')
def review_screen():
    pending=[s for s in all_scenes() if s.get('status','proposé')=='proposé']
    with ui.column().classes('w-full min-w-0 p-8 gap-5'):
        page_header('Validation humaine','Examinez les propositions avant de les retenir ou de les écarter.')
        with ui.card().classes('card p-4 w-full'):
            ui.label(f'{len(pending)} scènes en attente').classes('font-semibold')
            ui.label('Chaque scène reste une suggestion. Vérifiez son image, son contexte et les droits avant toute réutilisation.').classes('muted text-sm')
        if not pending:ui.label('Toutes les scènes proposées ont été examinées.').classes('muted')
        else:
            for scene in pending:scene_card(scene)
def workspace():
    with ui.row().classes('w-full min-h-screen no-wrap'):
        sidebar()
        with ui.column().classes('flex-1 min-w-0 min-h-screen'):
            if state['screen']=='dashboard':dashboard_screen()
            elif state['screen']=='collections':collections_screen()
            elif state['screen']=='review':review_screen()
            else:search_screen()
@ui.refreshable
def render():
    if state['screen']=='library':library_screen()
    else:workspace()
def keyboard(e):
    key=getattr(e,'key','')
    if key=='Escape':state['selected']=None;render.refresh()
    elif key=='/':ui.run_javascript("document.querySelector('input')?.focus()")
    elif key in ('ArrowDown','ArrowUp') and state['rows']:
        scenes=[r['scene'] for r in state['rows']];i=next((n for n,s in enumerate(scenes) if s is state['selected']),-1);i=max(0,min(len(scenes)-1,i+(1 if key=='ArrowDown' else -1)));state['selected']=scenes[i];render.refresh()
ui.keyboard(on_key=keyboard)
if state['screen']!='library':refresh_results(refresh_ui=False)
render()
ui.timer(0.4,sync_ingest_progress)
if state['screen']!='library':ui.timer(0.2,lambda:refresh_library(quiet=True),once=True)
ui.run(host='127.0.0.1',port=8080,title='ArchivIA',reload=False,show=True)
